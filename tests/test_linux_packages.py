import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'service'))
from channels import CHANNELS
spec = importlib.util.spec_from_file_location('package_linux', BASE / 'builder/package_linux.py')
package_linux = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package_linux)


class LinuxPackageTests(unittest.TestCase):
    def test_channels_install_without_file_conflicts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            (source / 'dist').mkdir(parents=True)
            (source / 'dist/Eglantine.png').write_bytes(b'icon fixture')
            (source / 'dist/dev.eden_emu.eden.desktop').write_text('[Desktop Entry]\nType=Application\nName=Eglantine\nIcon=dev.eglantine.eglantine\nExec=eglantine %f\nTryExec=eglantine\n')
            (source / 'LICENSE.txt').write_text('license fixture')
            keys = root / 'keys'
            keys.mkdir()
            (keys / 'eglantine-archive-keyring.gpg').write_bytes(b'public key fixture')
            files = {}
            for channel in CHANNELS:
                work = root / channel.name
                (work / 'AppDir/usr/bin').mkdir(parents=True)
                (work / 'AppDir/usr/bin/eglantine').write_text('#!/bin/sh\nexit 0\n')
                (work / 'AppDir/AppRun').symlink_to('usr/bin/eglantine')
                meta = package_linux.metadata(channel.package)
                for field in ('branch', 'prefix', 'appimage', 'title'):
                    self.assertEqual(meta[field], getattr(channel, field))
                package_linux.prepare_desktop(source, work, meta)
                self.assertIn('Exec=eglantine %f', (work / meta['desktop']).read_text())
                deb = package_linux.package_deb(source, work, root / 'out', keys, meta, '0~test.1', 'https://example.test')
                name = subprocess.check_output(['dpkg-deb', '-f', str(deb), 'Package'], text=True).strip()
                self.assertEqual(name, channel.package)
                contents = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(deb)])
                with tarfile.open(fileobj=io.BytesIO(contents)) as archive:
                    files[channel.name] = {item.name for item in archive.getmembers() if item.isfile() or item.issym()}
                desktop = (work / 'deb/usr/share/applications' / f'{channel.package}.desktop').read_text()
                self.assertIn(f'Name={channel.title}\n', desktop)
                self.assertIn(f'Exec={channel.package} %f\n', desktop)
                wrapper = (work / 'deb/usr/bin' / channel.package).read_text()
                self.assertIn(f'/opt/{channel.package}/AppRun', wrapper)
                self.assertTrue((work / f'deb/opt/{channel.package}/AppRun').is_symlink())
                apt = (work / f'deb/etc/apt/sources.list.d/{channel.package}.list').read_text()
                self.assertIn(f'https://example.test{channel.prefix}/apt', apt)
                self.assertIn(f'/usr/share/keyrings/{channel.package}-archive-keyring.gpg', apt)
            self.assertFalse(files['stable'] & files['nightly'])

if __name__ == '__main__': unittest.main()
