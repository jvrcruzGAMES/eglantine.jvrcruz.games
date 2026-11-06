#!/usr/bin/env python3
import datetime as dt
import argparse
import fcntl
import json
import hashlib
import logging
import os
from pathlib import Path
import re
import subprocess
import time
from config import DATA, ROOT, UPSTREAM, PUBLIC_URL
from channels import CHANNELS, STABLE
from publish import initialize_key, publish

PLATFORM = os.environ.get('BUILD_PLATFORM', 'linux')
logger = logging.getLogger('eglantine.worker')

def state(channel=STABLE, **changes):
    path = channel.storage(DATA, PLATFORM) / 'status.json'
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
    jobs_setting = os.environ.get('WINDOWS_BUILD_JOBS', '3') if PLATFORM == 'windows' else os.environ.get('BUILD_JOBS', '6')
    jobs = min(max(1, int(jobs_setting)), available)
    memory = os.environ.get('WINDOWS_BUILD_MEMORY') if PLATFORM == 'windows' else os.environ.get('BUILD_MEMORY')
    if not memory:
        # Leave host headroom when the two platform workers build concurrently.
        memory = str(min((8 if PLATFORM == 'windows' else 10) * 1024**3, int(info['MemTotal'] * (0.30 if PLATFORM == 'windows' else 0.60))))
    log.write(f'Docker build resources: jobs={jobs}, memory={memory} (daemon CPUs={available})\n')
    log.flush()
    return jobs, memory

def builder_revision():
    names = ['builder/common.sh', 'builder/incremental_build.py', 'service/channels.py']
    if PLATFORM == 'linux':
        names += ['builder/linux.sh', 'builder/package_linux.py', 'builder/Dockerfile', 'service/publish.py']
    else:
        names += [str(p.relative_to(ROOT)) for p in (ROOT / 'builder').iterdir() if p.is_file()]
        names += [str(p.relative_to(ROOT)) for p in (ROOT / 'windows').iterdir() if p.is_file()]
        names += ['service/publish_windows.py']
    digest = hashlib.sha256(PUBLIC_URL.encode())
    for name in sorted(set(names)):
        digest.update(name.encode()); digest.update((ROOT / name).read_bytes())
    return digest.hexdigest()


def needs_build(previous, sha, current_time, rebuild_seconds, revision=None):
    if revision is not None and previous.get('builder_revision') != revision:
        return True
    if previous.get('last_success') != sha:
        return True
    try:
        last_start = dt.datetime.fromisoformat(previous['last_success_started_at'])
        return (current_time - last_start).total_seconds() >= rebuild_seconds
    except (KeyError, ValueError, TypeError):
        return True


def build(sha, channel=STABLE):
    data = channel.storage(DATA, PLATFORM)
    version = dt.datetime.now(dt.timezone.utc).strftime('0~' + ('nx2' if channel.name == 'stable' else 'nightly') + '.%Y%m%d%H%M%S') + '+' + sha[:12]
    logs = data / 'public/logs'
    logs.mkdir(parents=True, exist_ok=True)
    logname = f'{version}.log'
    source = data / 'source'
    staging = data / 'staging' / version
    staging.mkdir(parents=True)
    started_at = now()
    revision = builder_revision()
    state(channel, phase='building', platform=PLATFORM, commit=sha, started_at=started_at, log=f'{channel.prefix}' + ('/windows' if PLATFORM == 'windows' else '') + f'/logs/{logname}', error=None)
    with (logs / logname).open('w', buffering=1) as log:
        if not (source / '.git').exists():
            call(['git', 'clone', '--depth', '1', '--no-checkout', '--branch', channel.branch, UPSTREAM, str(source)], log)
        call(['git', '-C', str(source), 'fetch', 'origin', channel.branch], log)
        call(['git', '-C', str(source), 'checkout', '--force', sha], log)
        call(['git', '-C', str(source), 'submodule', 'update', '--init', '--recursive'], log)
        image = 'eglantine-windows-builder:local' if PLATFORM == 'windows' else 'eglantine-builder:local'
        image_args = ['-f', str(ROOT / 'builder/Dockerfile.windows')] if PLATFORM == 'windows' else []
        call(['docker', 'build', *image_args, '-t', image, str(ROOT / 'builder')], log)
        jobs, memory = docker_resources(log)
        for platform in (PLATFORM,):
            state(channel, platform=platform)
            work = data / 'work' / platform
            cache = DATA / 'cache'
            for path in (work, cache): path.mkdir(parents=True, exist_ok=True)
            call(['docker', 'run', '--rm', '--name', f'{channel.package}-build-{platform}',
                  f'--memory={memory}', '--pids-limit=2048',
                  '-e', f'PUBLIC_URL={PUBLIC_URL}', '-e', f'PACKAGE_VERSION={version}',
                  '-e', f'BUILD_JOBS={jobs}',
                  '-e', f'PACKAGE_NAME={channel.package}',
                  '-e', f'BUILD_CHANNEL={channel.name}',
                  '-e', f'WINDOWS_PREBUILT_LIBS={os.environ.get("WINDOWS_PREBUILT_LIBS", "1")}',
                  *(['-v', f'{DATA / "mxe"}:/opt/mxe'] if PLATFORM == 'windows' else []),
                  '-v', f'{source}:/source', '-v', f'{work}:/work',
                  '-v', f'{cache}:/cache',
                  '-v', f'{staging}:/out',
                  *(['-v', f'{DATA / "keys"}:/keys:ro'] if PLATFORM == 'linux' else []),
                  '-v', f'{ROOT / "builder"}:/scripts:ro',
                  *(['-v', f'{ROOT / "windows"}:/harness:ro'] if PLATFORM == 'windows' else []),
                  image, 'bash', f'/scripts/{platform}.sh'], log)
        # Include the exact checkout, fetched dependency sources and build instructions.
        call(['tar', '--exclude=.git', '--exclude=__pycache__', '--exclude=*.pyc', '-czf', str(staging / 'source.tar.gz'),
              '-C', str(data), 'source', '-C', str(ROOT), 'builder', *(['windows'] if PLATFORM == 'windows' else [])], log)
        if PLATFORM == 'windows':
            from publish_windows import publish_windows
            release = publish_windows(staging, sha, version, channel)
        else:
            release = publish(staging, sha, version, channel)
    state(channel, phase='ready', platform=None, last_success=sha, release=release['version'],
          finished_at=now(), last_success_started_at=started_at, error=None, retry_at=None, builder_revision=revision)

def poll_channels(rebuild_seconds):
    for channel in CHANNELS:
        try:
            path = channel.storage(DATA, PLATFORM) / 'status.json'
            previous = json.loads(path.read_text()) if path.exists() else {}
            if previous.get('retry_at') and dt.datetime.fromisoformat(previous['retry_at']) > dt.datetime.now(dt.timezone.utc):
                logger.info('%s/%s: retry scheduled for %s', PLATFORM, channel.name, previous['retry_at'])
                continue
            logger.info('%s/%s: checking branch %s', PLATFORM, channel.name, channel.branch)
            result = subprocess.check_output(['git', 'ls-remote', UPSTREAM, f'refs/heads/{channel.branch}'],
                                             text=True, timeout=90).split()
            if not result or not re.fullmatch('[0-9a-f]{40}', result[0]):
                raise RuntimeError(f'Upstream branch {channel.branch} returned no commit')
            sha = result[0]
            state(channel, checked_at=now(), upstream_commit=sha)
            if needs_build(previous, sha, dt.datetime.now(dt.timezone.utc), rebuild_seconds, builder_revision()):
                logger.info('%s/%s: starting build of %s (commit, hourly or builder-change trigger)', PLATFORM, channel.name, sha)
                build(sha, channel)
                logger.info('%s/%s: build published', PLATFORM, channel.name)
            elif previous.get('phase') != 'ready':
                state(channel, phase='ready', error=None)
        except Exception as exc:
            logger.exception('%s/%s: check or build failed', PLATFORM, channel.name)
            retry_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(os.environ.get('RETRY_SECONDS', '1800')))
            state(channel, phase='failed', error=str(exc), finished_at=now(), retry_at=retry_at.isoformat())

def main(argv=None):
    global PLATFORM
    parser = argparse.ArgumentParser(description='Watch and build both Eglantine channels for one platform')
    parser.add_argument('--platform', choices=('linux', 'windows'), default=PLATFORM)
    PLATFORM = parser.parse_args(argv).platform
    if PLATFORM not in ('linux', 'windows'):
        parser.error('BUILD_PLATFORM must be linux or windows')
    DATA.mkdir(parents=True, exist_ok=True)
    lock = (DATA / ('worker-windows.lock' if PLATFORM == 'windows' else 'worker.lock')).open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    logs = STABLE.storage(DATA, PLATFORM) / 'public/logs'
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(), logging.FileHandler(logs / 'watcher.log')])
    interval = int(os.environ.get('POLL_SECONDS', '120'))
    rebuild_seconds = max(1, int(os.environ.get('REBUILD_SECONDS', '3600')))
    logger.info('%s watcher started: poll=%ss rebuild=%ss retry=%ss; checking immediately',
                PLATFORM, interval, rebuild_seconds, os.environ.get('RETRY_SECONDS', '1800'))
    if PLATFORM == 'linux': initialize_key()
    while True:
        poll_channels(rebuild_seconds)
        time.sleep(interval)

if __name__ == '__main__': main()
