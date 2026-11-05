"""Build a per-user NSIS installer and the payload consumed by its update launcher."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile


def build_installer(payload, work, out, source, harness, package, version, public_url, channel):
    title = 'Eglantine Nightly' if channel == 'nightly' else 'Eglantine'
    prefix = '/nightly' if channel == 'nightly' else ''
    if package != ('eglantine-nightly' if channel == 'nightly' else 'eglantine'):
        raise ValueError('Channel/package mismatch')
    out.mkdir(parents=True, exist_ok=True)
    archive = out / (package + '-Windows-x86_64.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip:
        for file in sorted(payload.rglob('*')):
            if file.is_file(): zip.write(file, file.relative_to(payload))
    with archive.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    staging = work / 'installer-harness'
    staging.mkdir(parents=True, exist_ok=True)
    compile = ['x86_64-w64-mingw32.shared-gcc', '-O2', '-static-libgcc', '-municode', '-mwindows',
               '-s', str(harness / 'launcher.c'), '-o', str(staging / 'Launcher.exe'), '-lcrypt32']
    subprocess.run(compile, check=True)
    shutil.copy2(harness / 'updater.ps1', staging / 'updater.ps1')
    (staging / 'install.json').write_text(json.dumps(dict(schema=1, channel=channel, package=package, title=title,
        feed=f'{public_url}{prefix}/windows/updates/latest.json')))
    (staging / 'current.json').write_text(json.dumps(dict(version=version, sha256=digest,
        published_at=dt.datetime.now(dt.timezone.utc).isoformat())))
    installer = out / (package + '-Windows-x86_64-Setup.exe')
    values = dict(TITLE=title, OUTPUT=str(installer), PACKAGE=package,
                  OTHER='eglantine' if channel == 'nightly' else 'eglantine-nightly', VERSION=version,
                  PAYLOAD_SHA=digest, PAYLOAD_DIR=str(payload), HARNESS_DIR=str(staging))
    subprocess.run(['makensis', '-V2', *[f'-D{key}={value}' for key,value in values.items()], str(harness / 'installer.nsi')], check=True)
    return installer, archive


if __name__ == '__main__':
    build_installer(Path('/work/windows-package'), Path('/work'), Path('/out'), Path('/source'),
                    Path('/harness'), os.environ['PACKAGE_NAME'], os.environ['PACKAGE_VERSION'],
                    os.environ['PUBLIC_URL'], os.environ['BUILD_CHANNEL'])
