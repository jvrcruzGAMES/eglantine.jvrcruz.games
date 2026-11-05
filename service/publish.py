import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from config import DATA, PUBLIC_URL

def run(*args, **kw):
    return subprocess.check_output(args, **kw)

def initialize_key():
    home = DATA / 'gnupg'
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(home, 0o700)
    if not (home / 'pubring.kbx').exists():
        run('gpg', '--homedir', str(home), '--batch', '--passphrase', '',
            '--quick-generate-key', 'Eglantine Build Archive <builds@jvrcruz.games>', 'rsa3072', 'sign', '0')
    keys = DATA / 'keys'
    keys.mkdir(exist_ok=True)
    exported = run('gpg', '--homedir', str(home), '--export')
    if not exported: raise RuntimeError('Archive signing key is missing')
    (keys / 'eglantine-archive-keyring.gpg').write_bytes(exported)
    return home

def publish(staging: Path, sha: str, version: str):
    home = initialize_key()
    artifacts = ('Eglantine-x86_64.AppImage', 'Eglantine-x86_64.AppImage.zsync',
                 'eglantine_amd64.deb', 'Eglantine-Windows-x86_64.zip', 'source.tar.gz')
    for name in artifacts:
        if not (staging / name).is_file() or not (staging / name).stat().st_size:
            raise RuntimeError(f'Missing artifact: {name}')
    releases = DATA / 'public/releases'
    releases.mkdir(parents=True, exist_ok=True)
    target = releases / version
    if target.exists(): raise RuntimeError(f'Release already exists: {version}')
    snapshot = staging / 'site'
    snapshot.mkdir()
    apt = snapshot / 'apt'
    pool = apt / 'pool/main/e/eglantine'
    pool.mkdir(parents=True, exist_ok=True)
    debname = f'eglantine_{version}_amd64.deb'
    shutil.copy2(staging / 'eglantine_amd64.deb', pool / debname)
    binary = apt / 'dists/stable/main/binary-amd64'
    binary.mkdir(parents=True, exist_ok=True)
    packages = run('apt-ftparchive', 'packages', 'pool', cwd=apt)
    for name, content in [('Packages', packages), ('Packages.gz', gzip.compress(packages, mtime=0))]:
        tmp = binary / (name + '.tmp')
        tmp.write_bytes(content)
        tmp.replace(binary / name)
        for algorithm in ('SHA256', 'SHA512'):
            digest = hashlib.new(algorithm.lower(), content).hexdigest()
            hashed = binary / 'by-hash' / algorithm / digest
            hashed.parent.mkdir(parents=True, exist_ok=True)
            if not hashed.exists(): hashed.write_bytes(content)
    dist = apt / 'dists/stable'
    for name in ('Release', 'InRelease', 'Release.gpg'):
        (dist / name).unlink(missing_ok=True)
    release = run('apt-ftparchive',
        '-o', 'APT::FTPArchive::Release::Origin=Eglantine',
        '-o', 'APT::FTPArchive::Release::Label=Eglantine nx2',
        '-o', 'APT::FTPArchive::Release::Suite=stable',
        '-o', 'APT::FTPArchive::Release::Codename=stable',
        '-o', 'APT::FTPArchive::Release::Architectures=amd64',
        '-o', 'APT::FTPArchive::Release::Components=main',
        '-o', 'APT::FTPArchive::Release::Acquire-By-Hash=yes',
        'release', 'dists/stable', cwd=apt)
    (dist / 'Release').write_bytes(release)
    for switches, name in [(['--clearsign'], 'InRelease'), (['--armor', '--detach-sign'], 'Release.gpg')]:
        run('gpg', '--homedir', str(home), '--batch', '--yes', *switches,
            '--output', str(dist / name), str(dist / 'Release'))
    updates = snapshot / 'updates'
    updates.mkdir()
    for name in artifacts[:2]: shutil.copy2(staging / name, updates / name)
    manifest = dict(commit=sha, branch='nx2', version=version,
                    published_at=dt.datetime.now(dt.timezone.utc).isoformat(), artifacts=[])
    for name in artifacts:
        p = staging / name
        with p.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        manifest['artifacts'].append(dict(name=name, bytes=p.stat().st_size, sha256=digest,
                                           url=f'/releases/{version}/{name}'))
    (staging / 'SHA256SUMS').write_text(''.join(f"{a['sha256']}  {a['name']}\n" for a in manifest['artifacts']))
    (snapshot / 'release.json').write_text(json.dumps(manifest, indent=2))
    staging.rename(target)
    public = DATA / 'public'
    temp = public / 'current.next'
    temp.unlink(missing_ok=True)
    temp.symlink_to(Path('releases') / version / 'site')
    temp.replace(public / 'current')
    # Cleanup only after the complete, signed replacement is publicly available.
    for old in releases.iterdir():
        if old != target and old.is_dir():
            shutil.rmtree(old)
    staging_root = DATA / 'staging'
    if staging_root.exists():
        for old in staging_root.iterdir():
            if old.is_dir():
                shutil.rmtree(old)
    return manifest
