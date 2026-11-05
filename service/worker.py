#!/usr/bin/env python3
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time
import traceback
from config import DATA, ROOT, UPSTREAM, PUBLIC_URL
from channels import CHANNELS, STABLE
from publish import initialize_key, publish

def state(channel=STABLE, **changes):
    path = channel.storage(DATA) / 'status.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    old = json.loads(path.read_text()) if path.exists() else {}
    old.update(changes)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(old, indent=2))
    tmp.replace(path)

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def call(args, log=None, **kw):
    try:
        return subprocess.run(args, check=True, stdout=log, stderr=subprocess.STDOUT if log else None, **kw)
    except subprocess.CalledProcessError as exc:
        if log is None:
            raise
        log.flush()
        with open(log.name, 'rb') as output:
            output.seek(0, os.SEEK_END)
            output.seek(max(0, output.tell() - 8192))
            tail = output.read().decode('utf-8', errors='replace').strip()
        raise RuntimeError(f'{args[0]} exited with status {exc.returncode}. Build log tail:\n{tail}') from exc


def docker_resources(log):
    try:
        info = json.loads(subprocess.check_output(
            ['docker', 'info', '--format', '{{json .}}'], text=True,
            stderr=subprocess.STDOUT, timeout=30))
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f'Cannot inspect Docker daemon: {exc.output.strip()}') from exc
    available = int(info['NCPU'])
    if available < 1:
        raise ValueError('Docker daemon CPU count must be positive')
    jobs = min(max(1, int(os.environ.get('BUILD_JOBS', '6'))), available)
    memory = os.environ.get('BUILD_MEMORY')
    if not memory:
        memory = str(min(10 * 1024**3, int(info['MemTotal'] * 0.75)))
    log.write(f'Docker build resources: jobs={jobs}, memory={memory} (daemon CPUs={available})\n')
    log.flush()
    return jobs, memory

def needs_build(previous, sha, current_time, rebuild_seconds):
    if previous.get('last_success') != sha:
        return True
    try:
        last_start = dt.datetime.fromisoformat(previous['last_success_started_at'])
        return (current_time - last_start).total_seconds() >= rebuild_seconds
    except (KeyError, ValueError, TypeError):
        return True


def build(sha, channel=STABLE):
    data = channel.storage(DATA)
    version = dt.datetime.now(dt.timezone.utc).strftime('0~' + ('nx2' if channel.name == 'stable' else 'nightly') + '.%Y%m%d%H%M%S') + '+' + sha[:12]
    logs = data / 'public/logs'
    logs.mkdir(parents=True, exist_ok=True)
    logname = f'{version}.log'
    source = data / 'source'
    staging = data / 'staging' / version
    staging.mkdir(parents=True)
    started_at = now()
    state(channel, phase='building', platform='linux', commit=sha, started_at=started_at, log=f'{channel.prefix}/logs/{logname}', error=None)
    with (logs / logname).open('w', buffering=1) as log:
        if not (source / '.git').exists():
            call(['git', 'clone', '--depth', '1', '--no-checkout', '--branch', channel.branch, UPSTREAM, str(source)], log)
        call(['git', '-C', str(source), 'fetch', 'origin', channel.branch], log)
        call(['git', '-C', str(source), 'checkout', '--force', sha], log)
        call(['git', '-C', str(source), 'submodule', 'update', '--init', '--recursive'], log)
        call(['docker', 'build', '-t', 'eglantine-builder:local', str(ROOT / 'builder')], log)
        jobs, memory = docker_resources(log)
        for platform in ('linux',):
            state(channel, platform=platform)
            work = data / 'work' / platform
            cache = DATA / 'cache'
            for path in (work, cache): path.mkdir(parents=True, exist_ok=True)
            call(['docker', 'run', '--rm', '--name', f'{channel.package}-build-{platform}',
                  f'--memory={memory}', '--pids-limit=2048',
                  '-e', f'PUBLIC_URL={PUBLIC_URL}', '-e', f'PACKAGE_VERSION={version}',
                  '-e', f'BUILD_JOBS={jobs}',
                  '-e', f'PACKAGE_NAME={channel.package}',
                  '-v', f'{source}:/source', '-v', f'{work}:/work',
                  '-v', f'{cache}:/cache',
                  '-v', f'{staging}:/out', '-v', f'{DATA / "keys"}:/keys:ro',
                  '-v', f'{ROOT / "builder"}:/scripts:ro',
                  'eglantine-builder:local', 'bash', f'/scripts/{platform}.sh'], log)
        # Include the exact checkout, fetched dependency sources and build instructions.
        call(['tar', '--exclude=.git', '--exclude=__pycache__', '--exclude=*.pyc', '-czf', str(staging / 'source.tar.gz'),
              '-C', str(data), 'source', '-C', str(ROOT), 'builder'], log)
        release = publish(staging, sha, version, channel)
    state(channel, phase='ready', platform=None, last_success=sha, release=release['version'],
          finished_at=now(), last_success_started_at=started_at, error=None, retry_at=None)

def poll_channels(rebuild_seconds):
    for channel in CHANNELS:
        try:
            path = channel.storage(DATA) / 'status.json'
            previous = json.loads(path.read_text()) if path.exists() else {}
            if previous.get('retry_at') and dt.datetime.fromisoformat(previous['retry_at']) > dt.datetime.now(dt.timezone.utc):
                continue
            result = subprocess.check_output(['git', 'ls-remote', UPSTREAM, f'refs/heads/{channel.branch}'],
                                             text=True, timeout=90).split()
            if not result or not re.fullmatch('[0-9a-f]{40}', result[0]):
                raise RuntimeError(f'Upstream branch {channel.branch} returned no commit')
            sha = result[0]
            state(channel, checked_at=now(), upstream_commit=sha)
            if needs_build(previous, sha, dt.datetime.now(dt.timezone.utc), rebuild_seconds):
                build(sha, channel)
            elif previous.get('phase') != 'ready':
                state(channel, phase='ready', error=None)
        except Exception as exc:
            traceback.print_exc()
            retry_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(os.environ.get('RETRY_SECONDS', '1800')))
            state(channel, phase='failed', error=str(exc), finished_at=now(), retry_at=retry_at.isoformat())

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    lock = (DATA / 'worker.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    initialize_key()
    interval = int(os.environ.get('POLL_SECONDS', '120'))
    rebuild_seconds = max(1, int(os.environ.get('REBUILD_SECONDS', '3600')))
    while True:
        poll_channels(rebuild_seconds)
        time.sleep(interval)

if __name__ == '__main__': main()
