"""Create channel-specific desktop files and Debian packages without file conflicts."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def metadata(package):
    if package == 'eglantine':
        return dict(package=package, title='Eglantine', branch='nx2', prefix='',
                    appimage='Eglantine-x86_64.AppImage', icon='dev.eglantine.eglantine',
                    desktop='dev.eden_emu.eden.desktop')
    if package == 'eglantine-nightly':
        return dict(package=package, title='Eglantine Nightly', branch='nx2-experimental', prefix='/nightly',
                    appimage='Eglantine-nightly-x86_64.AppImage', icon='dev.eglantine.eglantine-nightly',
                    desktop='eglantine-nightly.desktop')
    raise ValueError(f'Unsupported package: {package}')


def desktop_text(source, meta, executable):
    changes = {'Name': meta['title'], 'Icon': meta['icon'], 'Exec': executable + ' %f', 'TryExec': executable}
    return '\n'.join(key + '=' + changes[key] if (key := line.split('=', 1)[0]) in changes else line
                     for line in source.read_text().splitlines()) + '\n'


def prepare_desktop(source, work, meta):
    work.mkdir(parents=True, exist_ok=True)
    (work / meta['desktop']).write_text(desktop_text(source / 'dist/dev.eden_emu.eden.desktop', meta, 'eglantine'))
    shutil.copy2(source / 'dist/Eglantine.png', work / (meta['icon'] + '.png'))


def package_deb(source, work, out, keys, meta, version, public_url):
    package = meta['package']
    root = work / 'deb'
    if root.exists(): shutil.rmtree(root)
    for directory in (f'opt/{package}', 'usr/bin', 'usr/share/applications',
                      'usr/share/icons/hicolor/256x256/apps', 'DEBIAN', 'usr/share/keyrings',
                      'etc/apt/sources.list.d', f'usr/share/doc/{package}'):
        (root / directory).mkdir(parents=True, exist_ok=True)
    shutil.copytree(work / 'AppDir', root / f'opt/{package}', symlinks=True, dirs_exist_ok=True)
    launcher = root / f'usr/bin/{package}'
    launcher.write_text(f'#!/bin/sh\nexec /opt/{package}/AppRun "$@"\n')
    launcher.chmod(0o755)
    (root / f'usr/share/applications/{package}.desktop').write_text(
        desktop_text(source / 'dist/dev.eden_emu.eden.desktop', meta, package))
    shutil.copy2(source / 'dist/Eglantine.png', root / f'usr/share/icons/hicolor/256x256/apps/{meta["icon"]}.png')
    shutil.copy2(source / 'LICENSE.txt', root / f'usr/share/doc/{package}/copyright')
    keyname = 'eglantine-archive-keyring.gpg'
    shutil.copy2(keys / 'eglantine-archive-keyring.gpg', root / f'usr/share/keyrings/{keyname}')
    (root / 'etc/apt/sources.list.d/eglantine.list').write_text(
        f'deb [arch=amd64 signed-by=/usr/share/keyrings/{keyname}] {public_url}/apt stable main\n')
    (root / 'DEBIAN/control').write_text(f'''Package: {package}
Version: {version}
Section: games
Priority: optional
Conflicts: {'eglantine-nightly' if package == 'eglantine' else 'eglantine'}
Architecture: amd64
Maintainer: Eglantine builds <builds@jvrcruz.games>
Depends: libc6 (>= 2.39), libstdc++6, libgl1, libegl1, libvulkan1, libx11-6, libxcb1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0
Recommends: mesa-vulkan-drivers
Homepage: https://github.com/Eglantine-Community/Eglantine
Description: {meta['title']} {meta['branch']} development build
 Automatically built from the {meta['branch']} branch. Includes launcher integration and APT updates.
''')
    hooks = '''#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null; then update-desktop-database -q /usr/share/applications || true; fi
if command -v gtk-update-icon-cache >/dev/null; then gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true; fi
'''
    for name in ('postinst', 'postrm'):
        path = root / 'DEBIAN' / name
        path.write_text(hooks)
        path.chmod(0o755)
    out.mkdir(parents=True, exist_ok=True)
    output = out / (package + '_amd64.deb')
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(root), str(output)], check=True)
    return output


if __name__ == '__main__':
    meta = metadata(os.environ.get('PACKAGE_NAME', 'eglantine'))
    if sys.argv[1] == 'desktop':
        prepare_desktop(Path('/source'), Path('/work'), meta)
    elif sys.argv[1] == 'deb':
        package_deb(Path('/source'), Path('/work'), Path('/out'), Path('/keys'), meta,
                    os.environ['PACKAGE_VERSION'], os.environ['PUBLIC_URL'])
    else:
        raise SystemExit('Expected desktop or deb')
