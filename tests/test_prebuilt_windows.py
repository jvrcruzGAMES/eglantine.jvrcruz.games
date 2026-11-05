import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1] / 'builder'
def load(name):
    spec = importlib.util.spec_from_file_location(name, BASE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[name] = module
    return module

prebuilt = load('prebuilt_windows')
stager = load('windows_stage')


class PrebuiltWindowsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / 'qt-windows/6.8.3/mingw_64'
        self.host = self.root / 'qt/6.8.3/gcc_64'
        for name in ('lib/cmake/Qt6/Qt6Config.cmake', 'lib/cmake/Qt6Charts/Qt6ChartsConfig.cmake',
                     'bin/Qt6Core.dll', 'plugins/platforms/qwindows.dll'):
            path = self.target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        (self.host / 'bin').mkdir(parents=True)
        (self.host / 'bin/qmake').touch()

    def test_cached_kit_needs_no_download(self):
        with patch('prebuilt_windows.subprocess.run') as download, patch('prebuilt_windows.subprocess.check_output', return_value='6.8.3\n'):
            self.assertEqual(prebuilt.ensure_qt(self.root), (self.target, self.host))
        download.assert_not_called()

    def test_missing_charts_requests_a_complete_kit(self):
        (self.target / 'lib/cmake/Qt6Charts/Qt6ChartsConfig.cmake').unlink()
        with patch('prebuilt_windows.subprocess.run') as download:
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                prebuilt.ensure_qt(self.root)
        command = download.call_args.args[0]
        self.assertIn('win64_mingw', command)
        self.assertIn('qtcharts', command)

    def test_failed_compatibility_probe_selects_source_fallback(self):
        with patch('prebuilt_windows.ensure_qt', return_value=(self.target, self.host)), patch('prebuilt_windows.probe', side_effect=subprocess.CalledProcessError(1, ['cmake'])):
            self.assertFalse(prebuilt.select(self.root, BASE, self.root))

    def test_mismatched_host_version_selects_source_fallback(self):
        with patch('prebuilt_windows.subprocess.check_output', return_value='6.12.0\n'), patch('prebuilt_windows.probe') as probe:
            self.assertFalse(prebuilt.select(self.root, BASE, self.root))
        probe.assert_not_called()

    def test_verified_kit_is_selected(self):
        with patch('prebuilt_windows.ensure_qt', return_value=(self.target, self.host)), patch('prebuilt_windows.probe') as probe:
            self.assertTrue(prebuilt.select(self.root, BASE, self.root))
        probe.assert_called_once_with(self.target, self.host, BASE, self.root)

    def test_clean_packaging_preserves_app_data_and_discards_old_qt(self):
        source = self.root / 'bin'
        source.mkdir()
        for name in ('eglantine.exe', 'eden-cli.exe', 'nx2_switches.txt', 'Qt6Core.dll', 'libstdc++-6.dll'):
            (source / name).write_text(name)
        target = self.root / 'windows-package'
        (target / 'platforms').mkdir(parents=True)
        (target / 'platforms/old-plugin.dll').touch()
        stager.stage(source, target)
        self.assertEqual({p.name for p in target.iterdir()}, {'eglantine.exe', 'eden-cli.exe', 'nx2_switches.txt'})

if __name__ == '__main__': unittest.main()
