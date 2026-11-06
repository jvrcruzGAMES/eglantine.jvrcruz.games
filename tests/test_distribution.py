import functools
import http.client
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service'))
import config
import publish
import publish_windows
import server
from channels import STABLE, NIGHTLY

class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.temp.name)
        publish.DATA = publish_windows.DATA = server.DATA = cls.data
        cls.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown(); cls.http.server_close(); cls.temp.cleanup()
    def request(self, path, headers=None, method='GET'):
        conn = http.client.HTTPConnection('127.0.0.1', self.http.server_port)
        conn.request(method, path, headers=headers or {})
        res = conn.getresponse(); content = res.read()
        result = res.status, dict(res.getheaders()), content
        conn.close(); return result
    def stage(self, version, channel=STABLE):
        stage = channel.storage(self.data) / 'staging' / version
        stage.mkdir(parents=True)
        other = 'eglantine-nightly' if channel.package == 'eglantine' else 'eglantine'
        root = self.data / ('deb-' + version)
        (root / 'DEBIAN').mkdir(parents=True)
        (root / 'DEBIAN/control').write_text(f'Package: {channel.package}\nVersion: {version}\nArchitecture: amd64\nConflicts: {other}\nMaintainer: Test <test@example.com>\nDescription: Test\n')
        subprocess.run(['dpkg-deb','--build', str(root), str(stage / f'{channel.package}_amd64.deb')], check=True, stdout=subprocess.DEVNULL)
        for name in (channel.appimage, channel.appimage + '.zsync', 'source.tar.gz'):
            (stage / name).write_bytes(b'0123456789')
        return stage
    def test_distribution(self):
        self.assertEqual(self.request('/')[0], 200)
        self.assertIn(b'Windows installer', self.request('/')[2])
        self.assertEqual(json.loads(self.request('/api/status')[2])['latest'], None)
        one = publish.publish(self.stage('0~nx2.1+abc'), 'a'*40, '0~nx2.1+abc')
        self.assertNotIn('Eglantine-Windows-x86_64.zip', {a['name'] for a in one['artifacts']})
        first = (self.data / 'public/current').resolve()
        subprocess.run(['gpg', '--homedir', str(self.data / 'gnupg'), '--verify', str(first / 'apt/dists/stable/InRelease')], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        url = one['artifacts'][0]['url']
        status, headers, content = self.request(url, {'Range':'bytes=2-5'})
        self.assertEqual((status, content, headers['Content-Range']), (206,b'2345','bytes 2-5/10'))
        self.assertEqual(self.request(url, {'Range':'bytes=-3'})[2], b'789')
        self.assertEqual(self.request(url, {'Range':'bytes=100-'})[0],416)
        self.assertEqual(self.request(url, method='HEAD')[2],b'')
        status, headers, content = self.request(url, {'Range':'bytes=0-1,8-9'})
        self.assertEqual(status, 206)
        self.assertTrue(headers['Content-Type'].startswith('multipart/byteranges;'))
        self.assertEqual(int(headers['Content-Length']),len(content))
        self.assertIn(b'\r\n\r\n01\r\n',content)
        self.assertIn(b'\r\n\r\n89\r\n',content)
        self.assertEqual(self.request('/releases/%2e%2e/%2e%2e/gnupg/pubring.kbx')[0],404)
        self.assertEqual(self.request('/updates/Eglantine-x86_64.AppImage')[2],b'0123456789')
        legacy_zip = first.parent / 'Eglantine-Windows-x86_64.zip'
        legacy_zip.write_bytes(b'legacy Windows artifact')
        abandoned = self.stage('0~nx2.failed')
        publish.publish(self.stage('0~nx2.2+def'), 'b'*40, '0~nx2.2+def')
        self.assertFalse(abandoned.exists())
        self.assertFalse(first.exists())
        self.assertFalse(legacy_zip.exists())
        self.assertEqual(self.request(url)[0], 404)
        self.assertEqual(len(list((self.data / 'public/releases').iterdir())), 1)
        self.assertEqual(len(list((self.data / 'public/current/apt/pool/main/e/eglantine').glob('*.deb'))),1)
        packages = (self.data / 'public/current/apt/dists/stable/main/binary-amd64/Packages').read_text()
        self.assertIn('0~nx2.2+def', packages)
        self.assertNotIn('0~nx2.1+abc', packages)
        latest = json.loads(self.request('/api/status')[2])['latest']
        self.assertEqual(latest['commit'], 'b'*40)
        aptroot = self.data / 'client'
        (aptroot / 'lists/partial').mkdir(parents=True)
        (aptroot / 'cache/archives/partial').mkdir(parents=True)
        (aptroot / 'status').touch()
        sources = aptroot / 'sources.list'
        sources.write_text(f'deb [signed-by={self.data}/keys/eglantine-archive-keyring.gpg] http://127.0.0.1:{self.http.server_port}/apt stable main\n')
        options = ['-o', f'Dir::Etc::sourcelist={sources}', '-o', 'Dir::Etc::sourceparts=-',
                   '-o', f'Dir::State::lists={aptroot}/lists', '-o', f'Dir::State::status={aptroot}/status',
                   '-o', f'Dir::Cache={aptroot}/cache', '-o', f'APT::Sandbox::User={os.environ.get("USER", "root")}']
        subprocess.run(['apt-get', *options, 'update'], check=True, stdout=subprocess.DEVNULL)
        policy = subprocess.check_output(['apt-cache', *options, 'policy', 'eglantine'], text=True)
        self.assertIn('Candidate: 0~nx2.2+def', policy)

        failed = self.stage('0~nx2.3+ghi')
        real_run = publish.run
        def fail_signing(*args, **kwargs):
            if '--clearsign' in args:
                raise subprocess.CalledProcessError(1, args)
            return real_run(*args, **kwargs)
        with patch.object(publish, 'run', side_effect=fail_signing):
            with self.assertRaises(subprocess.CalledProcessError):
                publish.publish(failed, 'c'*40, '0~nx2.3+ghi')
        self.assertEqual(len(list((self.data / 'public/releases').iterdir())), 1)
        self.assertEqual(self.request('/updates/Eglantine-x86_64.AppImage')[0], 200)
        with self.assertRaises(RuntimeError): publish.publish(self.data / 'missing', 'c'*40, '0~nx2.3')
        # Publishing one channel must not remove or overwrite the other's artifacts or update feeds.
        nightly = publish.publish(self.stage('0~nightly.1+ddd', NIGHTLY), 'd'*40, '0~nightly.1+ddd', NIGHTLY)
        self.assertEqual(nightly['branch'], 'nx2-experimental')
        self.assertEqual(nightly['package'], 'eglantine-nightly')
        nightly_url = nightly['artifacts'][0]['url']
        self.assertEqual(self.request(nightly_url)[0], 200)
        self.assertEqual(self.request('/nightly/updates/' + NIGHTLY.appimage)[2], b'0123456789')
        self.assertEqual(self.request('/updates/' + NIGHTLY.appimage)[0], 404)
        self.assertEqual(self.request('/nightly/updates/' + STABLE.appimage)[0], 404)
        status = json.loads(self.request('/api/status')[2])
        self.assertEqual(status['channels']['nightly']['latest']['commit'], 'd'*40)
        self.assertEqual(status['channels']['stable']['latest']['commit'], 'b'*40)
        self.assertEqual(json.loads(self.request('/nightly/api/status')[2])['latest']['commit'], 'd'*40)
        self.assertEqual(self.request('/nightly/releases/%2e%2e/%2e%2e/gnupg/pubring.kbx')[0], 404)
        old_stable = status['latest']['artifacts'][0]['url']
        publish.publish(self.stage('0~nx2.4+eee'), 'e'*40, '0~nx2.4+eee')
        self.assertEqual(self.request(nightly_url)[0], 200)
        self.assertEqual(self.request(old_stable)[0], 404)
        publish.publish(self.stage('0~nightly.2+fff', NIGHTLY), 'f'*40, '0~nightly.2+fff', NIGHTLY)
        self.assertEqual(self.request(nightly_url)[0], 404)
        self.assertEqual(json.loads(self.request('/api/status')[2])['latest']['commit'], 'e'*40)
        nightly_packages = (self.data / 'nightly/public/current/apt/dists/stable/main/binary-amd64/Packages').read_text()
        self.assertIn('Package: eglantine-nightly\n', nightly_packages)
        self.assertIn('Package: eglantine\n', nightly_packages)
        self.assertIn(b'Package: eglantine-nightly\n', self.request('/apt/dists/stable/main/binary-amd64/Packages')[2])
        # One canonical signed repository offers both packages.
        subprocess.run(['apt-get', *options, 'update'], check=True, stdout=subprocess.DEVNULL)
        policy = subprocess.check_output(['apt-cache', *options, 'policy', 'eglantine', 'eglantine-nightly'], text=True)
        self.assertIn('Candidate: 0~nx2.4+eee', policy)
        self.assertIn('Candidate: 0~nightly.2+fff', policy)
        # The old nightly repository address remains a compatible alias.
        with sources.open('a') as file:
            file.write(f'deb [signed-by={self.data}/keys/eglantine-archive-keyring.gpg] http://127.0.0.1:{self.http.server_port}/nightly/apt stable main\n')
        subprocess.run(['apt-get', *options, 'update'], check=True, stdout=subprocess.DEVNULL)
        policy = subprocess.check_output(['apt-cache', *options, 'policy', 'eglantine', 'eglantine-nightly'], text=True)
        self.assertIn('Candidate: 0~nx2.4+eee', policy)
        self.assertIn('Candidate: 0~nightly.2+fff', policy)
        solver = subprocess.run(['apt-get', *options, '--simulate', 'install', 'eglantine', 'eglantine-nightly'], capture_output=True, text=True)
        self.assertNotEqual(solver.returncode, 0)
        self.assertIn('Conflicts', solver.stdout + solver.stderr)
        (aptroot / 'status').write_text('Package: eglantine\nStatus: install ok installed\nVersion: 0~nx2.4+eee\nArchitecture: amd64\nConflicts: eglantine-nightly\nMaintainer: Test <test@example.com>\nDescription: Test\n')
        switch = subprocess.check_output(['apt-get', *options, '--simulate', 'install', 'eglantine-nightly'], text=True)
        self.assertIn('Remv eglantine ', switch)
        self.assertIn('Inst eglantine-nightly ', switch)

        def windows_stage(version, channel):
            stage = channel.storage(self.data, 'windows') / 'staging' / version
            stage.mkdir(parents=True)
            for name in (channel.installer, channel.package + '-Windows-x86_64.zip', 'source.tar.gz'):
                (stage / name).write_bytes(b'windows fixture')
            return stage

        # Independent Windows publication cannot replace or delay Linux downloads.
        stable_linux = json.loads(self.request('/api/status')[2])['latest']
        windows_one = publish_windows.publish_windows(windows_stage('win.1', STABLE), '1'*40, 'win.1', STABLE)
        installer_url = windows_one['artifacts'][0]['url']
        self.assertEqual(self.request(installer_url)[2], b'windows fixture')
        feed = json.loads(self.request('/windows/updates/latest.json')[2])
        self.assertEqual(feed['channel'], 'stable')
        self.assertEqual(feed['payload'], windows_one['artifacts'][1])
        self.assertEqual(self.request(feed['payload']['url'])[2], b'windows fixture')
        self.assertEqual(json.loads(self.request('/api/status')[2])['latest'], stable_linux)
        nightly_windows = publish_windows.publish_windows(windows_stage('win.nightly.1', NIGHTLY), '2'*40, 'win.nightly.1', NIGHTLY)
        self.assertEqual(json.loads(self.request('/nightly/windows/updates/latest.json')[2])['package'], 'eglantine-nightly')
        self.assertEqual(json.loads(self.request('/api/status')[2])['channels']['nightly']['platforms']['windows']['latest'], nightly_windows)
        publish.publish(self.stage('0~nx2.5+999'), '9'*40, '0~nx2.5+999')
        self.assertEqual(self.request(installer_url)[0], 200)
        self.assertEqual(json.loads(self.request('/windows/api/status')[2])['latest'], windows_one)
        with self.assertRaises(RuntimeError):
            publish_windows.publish_windows(self.data / 'missing', '3'*40, 'win.failed', STABLE)
        self.assertEqual(self.request(installer_url)[0], 200)
        publish_windows.publish_windows(windows_stage('win.2', STABLE), '4'*40, 'win.2', STABLE)
        self.assertEqual(self.request(installer_url)[0], 404)
        self.assertEqual(self.request(nightly_windows['artifacts'][0]['url'])[0], 200)
        self.assertEqual(json.loads(self.request('/api/status')[2])['latest']['commit'], '9'*40)
        self.assertEqual(len(list((self.data / 'windows/public/releases').iterdir())), 1)
        self.assertEqual(self.request('/windows/releases/%2e%2e/%2e%2e/source/.git/config')[0], 404)

    def test_windows_log_button_before_and_during_builds(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, 'DATA', Path(directory)):
            page = self.request('/')[2]
            self.assertIn(b'id="windows-log" href="/windows/logs/latest.log"', page)
            self.assertNotIn(b'id="windows-log" hidden', page)
            self.assertIn(b'No Windows build has started', self.request('/windows/logs/latest.log')[2])
            watcher = Path(directory) / 'windows/public/logs/watcher.log'
            watcher.parent.mkdir(parents=True)
            watcher.write_text('windows/stable: checking branch nx2\n')
            self.assertEqual(self.request('/windows/logs/latest.log')[2], watcher.read_bytes())
            self.assertEqual(self.request('/nightly/windows/logs/latest.log')[2], watcher.read_bytes())
            for channel in (STABLE, NIGHTLY):
                data = channel.storage(Path(directory), 'windows')
                logs = data / 'public/logs'
                logs.mkdir(parents=True, exist_ok=True)
                (logs / 'attempt.log').write_text(channel.package + ' build in progress')
                (data / 'status.json').write_text(json.dumps(dict(phase='building', log=channel.prefix+'/windows/logs/attempt.log')))
                url = channel.prefix+'/windows/logs/latest.log'
                status, headers, content = self.request(url)
                self.assertEqual(status, 200)
                self.assertEqual(content.decode(), channel.package + ' build in progress')
                self.assertEqual(headers['Cache-Control'], 'no-cache')
                self.assertEqual(headers['Content-Type'], 'text/plain; charset=utf-8')
                self.assertEqual(self.request(url, method='HEAD')[2], b'')
                state = json.loads(self.request(channel.prefix+'/windows/api/status')[2])
                self.assertEqual(state['log_url'], url)


if __name__ == '__main__': unittest.main()
