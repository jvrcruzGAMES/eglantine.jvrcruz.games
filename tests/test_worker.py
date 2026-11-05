import datetime as dt
import io
import json
import os
import subprocess
import tempfile
from unittest.mock import patch
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service'))
from worker import needs_build, docker_resources, call

class SchedulingTests(unittest.TestCase):
    def test_commit_changes_and_hourly_rebuilds(self):
        started = dt.datetime(2026, 11, 5, tzinfo=dt.timezone.utc)
        previous = {'last_success': 'a' * 40, 'last_success_started_at': started.isoformat()}
        self.assertFalse(needs_build(previous, 'a' * 40, started + dt.timedelta(seconds=3599), 3600))
        self.assertTrue(needs_build(previous, 'a' * 40, started + dt.timedelta(hours=1), 3600))
        self.assertTrue(needs_build(previous, 'b' * 40, started, 3600))
        self.assertTrue(needs_build({}, 'a' * 40, started, 3600))
        # Migrate old state without a scheduling timestamp by rebuilding once.
        self.assertTrue(needs_build({'last_success': 'a' * 40}, 'a' * 40, started, 3600))
        self.assertTrue(needs_build(previous, 'a' * 40, started + dt.timedelta(seconds=60), 60))

class DockerStartupTests(unittest.TestCase):
    def test_small_server_resources(self):
        info = json.dumps({'NCPU': 2, 'MemTotal': 4 * 1024**3})
        with patch.dict(os.environ, {}, clear=True), patch('worker.subprocess.check_output', return_value=info):
            jobs, memory = docker_resources(io.StringIO())
        self.assertEqual(jobs, 2)
        self.assertEqual(int(memory), 3 * 1024**3)

    def test_resource_overrides(self):
        info = json.dumps({'NCPU': 4, 'MemTotal': 16 * 1024**3})
        with patch.dict(os.environ, {'BUILD_JOBS':'3', 'BUILD_MEMORY':'4g'}, clear=True), patch('worker.subprocess.check_output', return_value=info):
            self.assertEqual(docker_resources(io.StringIO()), (3, '4g'))

    def test_docker_error_is_in_exception(self):
        with tempfile.NamedTemporaryFile(mode='w') as log:
            with self.assertRaisesRegex(RuntimeError, 'daemon startup reason'):
                call([sys.executable, '-c', 'import sys; print("daemon startup reason", file=sys.stderr); sys.exit(125)'], log)

    def test_daemon_access_error_is_reported(self):
        error = subprocess.CalledProcessError(1, ['docker', 'info'], output='permission denied on Docker socket')
        with patch('worker.subprocess.check_output', side_effect=error):
            with self.assertRaisesRegex(RuntimeError, 'permission denied on Docker socket'):
                docker_resources(io.StringIO())

if __name__ == '__main__': unittest.main()
