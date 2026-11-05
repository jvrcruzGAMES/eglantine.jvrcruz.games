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
    return subprocess.run(args, check=True, stdout=log, stderr=subprocess.STDOUT if log else None, **kw)

def build(sha):
    version = dt.datetime.now(dt.timezone.utc).strftime('0~nx2.%Y%m%d%H%M%S') + '+' + sha[:12]
    logs = DATA / 'public/logs'
    logs.mkdir(parents=True, exist_ok=True)
    logname = f'{version}.log'
    source = DATA / 'source'
    staging = DATA / 'staging' / version
    staging.mkdir(parents=True)
    state(phase='building', commit=sha, started_at=now(), log=f'/logs/{logname}', error=None)
    with (logs / logname).open('w', buffering=1) as log:
        if not (source / '.git').exists():
            call(['git', 'clone', '--depth', '1', '--no-checkout', '--branch', BRANCH, UPSTREAM, str(source)], log)
        call(['git', '-C', str(source), 'fetch', 'origin', BRANCH], log)
        call(['git', '-C', str(source), 'checkout', '--force', sha], log)
        call(['git', '-C', str(source), 'submodule', 'update', '--init', '--recursive'], log)
        call(['docker', 'build', '-t', 'eglantine-builder:local', str(ROOT / 'builder')], log)
        for platform in ('linux', 'windows'):
            state(platform=platform)
            work = DATA / 'work' / platform
            cache = DATA / 'cache'
            mxe = DATA / 'mxe'
            for path in (work, cache, mxe): path.mkdir(parents=True, exist_ok=True)
            call(['docker', 'run', '--rm', '--name', f'eglantine-build-{platform}',
                  '--memory=10g', '--cpus=6', '--pids-limit=2048',
                  '-e', f'PUBLIC_URL={PUBLIC_URL}', '-e', f'PACKAGE_VERSION={version}',
                  '-e', f'BUILD_JOBS={os.environ.get("BUILD_JOBS", "6")}',
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
          finished_at=now(), error=None)

def main():
    DATA.mkdir(parents=True, exist_ok=True)
    lock = (DATA / 'worker.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    initialize_key()
    interval = int(os.environ.get('POLL_SECONDS', '120'))
    while True:
        try:
            result = subprocess.check_output(['git', 'ls-remote', UPSTREAM, f'refs/heads/{BRANCH}'],
                                             text=True, timeout=90).split()
            if not result or not re.fullmatch('[0-9a-f]{40}', result[0]):
                raise RuntimeError('Upstream branch returned no commit')
            sha = result[0]
            previous = json.loads(STATE.read_text()) if STATE.exists() else {}
            state(checked_at=now(), upstream_commit=sha)
            if previous.get('last_success') != sha:
                build(sha)
            elif previous.get('phase') != 'ready': state(phase='ready', error=None)
        except Exception as exc:
            traceback.print_exc()
            state(phase='failed', error=str(exc), finished_at=now())
            time.sleep(int(os.environ.get('RETRY_SECONDS', '1800')))
        time.sleep(interval)

if __name__ == '__main__': main()
