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
from config import DATA, ROOT, UPSTREAM, BRANCH, PUBLIC_URL
from publish import initialize_key, publish

STATE = DATA / 'status.json'
def state(**changes):
    old = json.loads(STATE.read_text()) if STATE.exists() else {}
    old.update(changes)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(old, indent=2))
    tmp.replace(STATE)

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


def build(sha):
    version = dt.datetime.now(dt.timezone.utc).strftime('0~nx2.%Y%m%d%H%M%S') + '+' + sha[:12]
    logs = DATA / 'public/logs'
    logs.mkdir(parents=True, exist_ok=True)
    logname = f'{version}.log'
    source = DATA / 'source'
    staging = DATA / 'staging' / version
    staging.mkdir(parents=True)
    started_at = now()
    state(phase='building', commit=sha, started_at=started_at, log=f'/logs/{logname}', error=None)
    with (logs / logname).open('w', buffering=1) as log:
        if not (source / '.git').exists():
            call(['git', 'clone', '--depth', '1', '--no-checkout', '--branch', BRANCH, UPSTREAM, str(source)], log)
        call(['git', '-C', str(source), 'fetch', 'origin', BRANCH], log)
        call(['git', '-C', str(source), 'checkout', '--force', sha], log)
        call(['git', '-C', str(source), 'submodule', 'update', '--init', '--recursive'], log)
        call(['docker', 'build', '-t', 'eglantine-builder:local', str(ROOT / 'builder')], log)
        jobs, memory = docker_resources(log)
        for platform in ('linux', 'windows'):
            state(platform=platform)
            work = DATA / 'work' / platform
            cache = DATA / 'cache'
            mxe = DATA / 'mxe'
            for path in (work, cache, mxe): path.mkdir(parents=True, exist_ok=True)
            call(['docker', 'run', '--rm', '--name', f'eglantine-build-{platform}',
                  f'--memory={memory}', '--pids-limit=2048',
                  '-e', f'PUBLIC_URL={PUBLIC_URL}', '-e', f'PACKAGE_VERSION={version}',
                  '-e', f'BUILD_JOBS={jobs}',
                  '-e', f'WINDOWS_PREBUILT_LIBS={os.environ.get("WINDOWS_PREBUILT_LIBS", "1")}',
                  '-e', f'MXE_PREBUILT_HOST_QT={os.environ.get("MXE_PREBUILT_HOST_QT", "1")}',
                  '-v', f'{source}:/source', '-v', f'{work}:/work',
                  '-v', f'{cache}:/cache', '-v', f'{mxe}:/opt/mxe',
                  '-v', f'{staging}:/out', '-v', f'{DATA / "keys"}:/keys:ro',
                  '-v', f'{ROOT / "builder"}:/scripts:ro',
                  'eglantine-builder:local', 'bash', f'/scripts/{platform}.sh'], log)
        # Include the exact checkout, fetched dependency sources and build instructions.
        call(['tar', '--exclude=.git', '-czf', str(staging / 'source.tar.gz'),
              '-C', str(DATA), 'source', '-C', str(ROOT), 'builder'], log)
        release = publish(staging, sha, version)
    state(phase='ready', platform=None, last_success=sha, release=release['version'],
          finished_at=now(), last_success_started_at=started_at, error=None)

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    lock = (DATA / 'worker.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    initialize_key()
    interval = int(os.environ.get('POLL_SECONDS', '120'))
    rebuild_seconds = max(1, int(os.environ.get('REBUILD_SECONDS', '3600')))
    while True:
        try:
            result = subprocess.check_output(['git', 'ls-remote', UPSTREAM, f'refs/heads/{BRANCH}'],
                                             text=True, timeout=90).split()
            if not result or not re.fullmatch('[0-9a-f]{40}', result[0]):
                raise RuntimeError('Upstream branch returned no commit')
            sha = result[0]
            previous = json.loads(STATE.read_text()) if STATE.exists() else {}
            state(checked_at=now(), upstream_commit=sha)
            if needs_build(previous, sha, dt.datetime.now(dt.timezone.utc), rebuild_seconds):
                build(sha)
            elif previous.get('phase') != 'ready': state(phase='ready', error=None)
        except Exception as exc:
            traceback.print_exc()
            state(phase='failed', error=str(exc), finished_at=now())
            time.sleep(int(os.environ.get('RETRY_SECONDS', '1800')))
        time.sleep(interval)

if __name__ == '__main__': main()
