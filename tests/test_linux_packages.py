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
    def test_current_and_legacy_desktop_templates(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'dist').mkdir()
            with self.assertRaisesRegex(FileNotFoundError, 'No supported Eglantine desktop template'):
                package_linux.desktop_template(source)
            legacy = source / 'dist/dev.eden_emu.eden.desktop'
            current = source / 'dist/dev.eglantine.eglantine.desktop'
            legacy.write_text('[Desktop Entry]\nName=Legacy\n')
            self.assertEqual(package_linux.desktop_template(source), legacy)
            current.write_text('[Desktop Entry]\nName=Eglantine\n')
            self.assertEqual(package_linux.desktop_template(source), current)

    def test_channels_have_distinct_files_but_conflict_by_package_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            (source / 'dist').mkdir(parents=True)
            (source / 'dist/Eglantine.png').write_bytes(b'icon fixture')
            (source / 'dist/dev.eglantine.eglantine.desktop').write_text('[Desktop Entry]\nType=Application\nName=Eglantine\nIcon=dev.eglantine.eglantine\nExec=eglantine %f\nTryExec=eglantine\n')
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
                conflicts = subprocess.check_output(['dpkg-deb','-f',str(deb),'Conflicts'],text=True).strip()
                self.assertEqual(conflicts, 'eglantine-nightly' if channel.package == 'eglantine' else 'eglantine')
                contents = subprocess.check_output(['dpkg-deb', '--fsys-tarfile', str(deb)])
                with tarfile.open(fileobj=io.BytesIO(contents)) as archive:
                    files[channel.name] = {item.name for item in archive.getmembers() if item.isfile() or item.issym()}
                desktop = (work / 'deb/usr/share/applications' / f'{channel.package}.desktop').read_text()
                self.assertIn(f'Name={channel.title}\n', desktop)
                self.assertIn(f'Exec={channel.package} %f\n', desktop)
                wrapper = (work / 'deb/usr/bin' / channel.package).read_text()
                self.assertIn(f'/opt/{channel.package}/AppRun', wrapper)
                self.assertTrue((work / f'deb/opt/{channel.package}/AppRun').is_symlink())
                apt = (work / 'deb/etc/apt/sources.list.d/eglantine.list').read_text()
                self.assertIn('https://example.test/apt', apt)
                self.assertIn('/usr/share/keyrings/eglantine-archive-keyring.gpg', apt)
            self.assertEqual(files['stable'] & files['nightly'], {'./etc/apt/sources.list.d/eglantine.list', './usr/share/keyrings/eglantine-archive-keyring.gpg'})

if __name__ == '__main__': unittest.main()
