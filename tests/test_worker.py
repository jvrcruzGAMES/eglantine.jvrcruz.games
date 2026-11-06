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
    def test_only_changes_trigger_builds(self):
        previous = {'last_success': 'a' * 40, 'builder_revision': 'current',
                    'last_success_started_at': '2000-01-01T00:00:00+00:00'}
        self.assertFalse(needs_build(previous, 'a' * 40, 'current'))
        self.assertFalse(needs_build({'last_success': 'a' * 40}, 'a' * 40))
        self.assertTrue(needs_build(previous, 'b' * 40, 'current'))
        self.assertTrue(needs_build(previous, 'a' * 40, 'changed'))
        self.assertTrue(needs_build({}, 'a' * 40, 'current'))

class DockerStartupTests(unittest.TestCase):
    def test_small_server_resources(self):
        info = json.dumps({'NCPU': 2, 'MemTotal': 4 * 1024**3})
        with patch.dict(os.environ, {}, clear=True), patch('worker.subprocess.check_output', return_value=info):
            jobs, memory = docker_resources(io.StringIO())
        self.assertEqual(jobs, 2)
        self.assertEqual(int(memory), int(4 * 1024**3 * 0.60))

    def test_concurrent_platform_memory_budgets(self):
        import worker
        info = json.dumps({'NCPU': 4, 'MemTotal': 8 * 1024**3})
        with patch.dict(os.environ, {}, clear=True), patch('worker.subprocess.check_output', return_value=info):
            with patch.object(worker, 'PLATFORM', 'linux'):
                linux = docker_resources(io.StringIO())
            with patch.object(worker, 'PLATFORM', 'windows'):
                windows = docker_resources(io.StringIO())
        self.assertEqual(windows[0], 3)
        self.assertLess(int(linux[1]) + int(windows[1]), 8 * 1024**3)

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


class ChannelSchedulingTests(unittest.TestCase):
    def test_same_triggers_for_both_platforms_and_branches(self):
        import worker
        from channels import CHANNELS
        current = dt.datetime.now(dt.timezone.utc)
        ready = dict(last_success='a'*40, last_success_started_at=current.isoformat(), builder_revision='current')
        cases = [
            ('first build', {}, True),
            ('unchanged', ready, False),
            ('commit change', dict(ready, last_success='b'*40), True),
            ('unchanged after years', dict(ready, last_success_started_at='2000-01-01T00:00:00+00:00'), False),
            ('builder change', dict(ready, builder_revision='old'), True),
            ('retry due', dict(ready, last_success='b'*40, retry_at=(current-dt.timedelta(seconds=1)).isoformat()), True),
            ('retry pending', dict(ready, retry_at=(current+dt.timedelta(hours=1)).isoformat()), False),
        ]
        for platform in ('linux', 'windows'):
            for label, previous, expected in cases:
                with self.subTest(platform=platform, trigger=label), tempfile.TemporaryDirectory() as directory, patch.object(worker, 'DATA', Path(directory)), patch.object(worker, 'PLATFORM', platform), patch.object(worker, 'builder_revision', return_value='current'):
                    for channel in CHANNELS:
                        worker.state(channel, **previous)
                    with patch.object(worker.subprocess, 'check_output', return_value='a'*40 + '\tref'), patch.object(worker, 'build') as builds:
                        worker.poll_channels()
                    self.assertEqual([call.args[1] for call in builds.call_args_list], list(CHANNELS) if expected else [])

    def test_platform_argument_overrides_environment_and_polls_immediately(self):
        import worker
        class StopPolling(Exception): pass
        for platform in ('linux', 'windows'):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory, patch.object(worker, 'DATA', Path(directory)), patch.object(worker, 'PLATFORM', 'windows' if platform == 'linux' else 'linux'), patch.dict(os.environ, {}, clear=True), patch.object(worker, 'initialize_key') as key, patch.object(worker.logging, 'basicConfig') as configure, patch.object(worker, 'poll_channels', side_effect=StopPolling) as poll, patch.object(worker.time, 'sleep') as sleep:
                with self.assertRaises(StopPolling):
                    worker.main(['--platform', platform])
                poll.assert_called_once_with()
                sleep.assert_not_called()
                self.assertEqual(key.call_count, int(platform == 'linux'))
                for handler in configure.call_args.kwargs['handlers']: handler.close()

    def test_failed_channel_does_not_delay_other_channel(self):
        import worker
        from channels import STABLE, NIGHTLY
        with tempfile.TemporaryDirectory() as directory, patch.object(worker, 'DATA', Path(directory)):
            def fake_build(sha, channel):
                if channel == STABLE:
                    raise RuntimeError('stable build failed')
                worker.state(channel, phase='ready', last_success=sha,
                             last_success_started_at=worker.now(), builder_revision=worker.builder_revision())
            with patch.object(worker.subprocess, 'check_output', side_effect=['a'*40 + '\trefs/heads/nx2', 'b'*40 + '\trefs/heads/nx2-experimental']) as remote, patch.object(worker, 'build', side_effect=fake_build) as builds:
                worker.poll_channels()
            self.assertEqual([call.args[1] for call in builds.call_args_list], [STABLE, NIGHTLY])
            self.assertEqual(remote.call_args_list[1].args[0][-1], 'refs/heads/nx2-experimental')
            stable = json.loads((Path(directory) / 'status.json').read_text())
            nightly = json.loads((Path(directory) / 'nightly/status.json').read_text())
            self.assertEqual(stable['phase'], 'failed')
            self.assertEqual(nightly['phase'], 'ready')
            with patch.object(worker.subprocess, 'check_output', return_value='b'*40 + '\trefs/heads/nx2-experimental') as remote, patch.object(worker, 'build') as builds:
                worker.poll_channels()
            self.assertEqual(remote.call_count, 1)
            self.assertEqual(remote.call_args.args[0][-1], 'refs/heads/nx2-experimental')
            builds.assert_not_called()

if __name__ == '__main__': unittest.main()
