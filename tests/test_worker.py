import datetime as dt
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'service'))
from worker import needs_build

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

if __name__ == '__main__': unittest.main()
