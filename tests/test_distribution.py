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
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service'))
import config
import publish
import server

class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.temp.name)
        publish.DATA = server.DATA = cls.data
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
    def stage(self, version):
        stage = self.data / 'staging' / version
        stage.mkdir(parents=True)
        root = self.data / ('deb-' + version)
        (root / 'DEBIAN').mkdir(parents=True)
        (root / 'DEBIAN/control').write_text(f'Package: eglantine\nVersion: {version}\nArchitecture: amd64\nMaintainer: Test <test@example.com>\nDescription: Test\n')
        subprocess.run(['dpkg-deb','--build', str(root), str(stage / 'eglantine_amd64.deb')], check=True, stdout=subprocess.DEVNULL)
        for name in ('Eglantine-x86_64.AppImage','Eglantine-x86_64.AppImage.zsync','Eglantine-Windows-x86_64.zip','source.tar.gz'):
            (stage / name).write_bytes(b'0123456789')
        return stage
    def test_distribution(self):
        self.assertEqual(self.request('/')[0], 200)
        self.assertEqual(json.loads(self.request('/api/status')[2])['latest'], None)
        one = publish.publish(self.stage('0~nx2.1+abc'), 'a'*40, '0~nx2.1+abc')
        first = (self.data / 'public/current').resolve()
        original = (first / 'apt/dists/stable/main/binary-amd64/Packages').read_bytes()
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
        publish.publish(self.stage('0~nx2.2+def'), 'b'*40, '0~nx2.2+def')
        self.assertEqual((first / 'apt/dists/stable/main/binary-amd64/Packages').read_bytes(),original)
        self.assertEqual(len(list((self.data / 'public/current/apt/pool/main/e/eglantine').glob('*.deb'))),2)
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

        with self.assertRaises(RuntimeError): publish.publish(self.data / 'missing', 'c'*40, '0~nx2.3')
        self.assertEqual(json.loads(self.request('/api/status')[2])['latest']['commit'],'b'*40)

if __name__ == '__main__': unittest.main()
