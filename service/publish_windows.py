import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
from config import DATA, PUBLIC_URL


def publish_windows(staging, sha, version, channel):
    data = channel.storage(DATA, 'windows')
    names = (channel.installer, channel.package + '-Windows-x86_64.zip', 'source.tar.gz')
    for name in names:
        if not (staging / name).is_file() or not (staging / name).stat().st_size:
            raise RuntimeError(f'Missing Windows artifact: {name}')
    prefix = channel.prefix + '/windows'
    manifest = dict(channel=channel.name, package=channel.package, branch=channel.branch,
                    platform='windows', commit=sha, version=version,
                    published_at=dt.datetime.now(dt.timezone.utc).isoformat(), artifacts=[])
    for name in names:
        file = staging / name
        with file.open('rb') as stream: digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        manifest['artifacts'].append(dict(name=name, bytes=file.stat().st_size, sha256=digest,
                                         url=f'{prefix}/releases/{version}/{name}'))
    site = staging / 'site'
    (site / 'updates').mkdir(parents=True)
    payload = next(a for a in manifest['artifacts'] if a['name'].endswith('.zip'))
    feed = dict(schema=1, channel=channel.name, package=channel.package, platform='windows',
                version=version, published_at=manifest['published_at'], payload=payload)
    (site / 'updates/latest.json').write_text(json.dumps(feed, indent=2))
    (site / 'release.json').write_text(json.dumps(manifest, indent=2))
    (staging / 'SHA256SUMS').write_text(''.join(f"{a['sha256']}  {a['name']}\n" for a in manifest['artifacts']))
    releases = data / 'public/releases'
    releases.mkdir(parents=True, exist_ok=True)
    target = releases / version
    if target.exists(): raise RuntimeError(f'Windows release already exists: {version}')
    staging.rename(target)
    public = data / 'public'
    link = public / 'current.next'
    link.unlink(missing_ok=True)
    link.symlink_to(Path('releases') / version / 'site')
    link.replace(public / 'current')
    for old in releases.iterdir():
        if old.is_dir() and old != target: shutil.rmtree(old)
    for old in (data / 'staging').iterdir():
        if old.is_dir(): shutil.rmtree(old)
    return manifest
