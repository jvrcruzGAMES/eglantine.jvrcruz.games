import importlib.util
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('mxe_setup', Path(__file__).resolve().parents[1] / 'builder/mxe_setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
sys.modules['mxe_setup'] = setup
SCRIPTS = Path(__file__).resolve().parents[1] / 'builder'


class ToolchainCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'src/qt/qt6').mkdir(parents=True)
        (self.root / 'src/qt/qt6/qt6-qtcharts.mk').write_text('deps := cc qt6-qtbase qt6-qtdeclarative\n')
        (self.root / 'src/qt/qt6/qt6-qtbase.mk').write_text('original Qt recipe')
        (self.root / 'src/boost.mk').write_text('--without-mpi --without-python\n')
        self.installed = self.root / 'usr/x86_64-w64-mingw32.shared/installed'
        self.installed.mkdir(parents=True)

    def test_repeated_setup_preserves_recipe_mtimes(self):
        setup.prepare(self.root, SCRIPTS)
        before = {p: p.stat().st_mtime_ns for p in (self.root / 'src').rglob('*.mk')}
        setup.prepare(self.root, SCRIPTS)
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in before})

    def test_existing_qt_and_boost_are_preserved(self):
        for package in ('qt6-qtbase', 'boost'):
            (self.installed / package).touch()
        setup.prepare(self.root, SCRIPTS)
        self.assertEqual((self.root / 'src/qt/qt6/qt6-qtbase.mk').read_text(), 'original Qt recipe')
        self.assertEqual((self.root / 'src/boost.mk').read_text(), '--without-mpi --without-python\n')

    def test_fresh_setup_reduces_unused_dependencies(self):
        setup.prepare(self.root, SCRIPTS)
        recipe = (self.root / 'src/qt/qt6/qt6-qtbase.mk').read_text()
        deps = next(line for line in recipe.splitlines() if line.startswith('$(PKG)_DEPS '))
        for package in ('mariadb', 'mesa', 'glib', 'icu4c', 'dbus'):
            self.assertNotIn(package, deps)
        self.assertIn('FEATURE_sql=OFF', recipe)
        self.assertIn('--with-filesystem', (self.root / 'src/boost.mk').read_text())
        self.assertTrue((self.root / 'src/dav1d.mk').exists())

    def test_cached_prebuilt_native_qt_is_registered_without_download(self):
        host = self.root / 'cache/qt-mxe/6.12.0/gcc_64'
        (host / 'bin').mkdir(parents=True)
        (host / 'bin/qmake').touch()
        with patch('mxe_setup.subprocess.check_output', side_effect=['x86_64-pc-linux-gnu\n', '6.12.0\n']), patch('mxe_setup.subprocess.run') as download:
            setup.bootstrap_native_tools(self.root, self.root / 'cache')
        download.assert_not_called()
        prefix = self.root / 'usr/x86_64-pc-linux-gnu'
        self.assertEqual((prefix / 'qt6').resolve(), host)
        self.assertTrue((prefix / 'installed/cmake').exists())
        self.assertTrue((prefix / 'installed/qt6-qtbase').exists())

    def test_unusable_prebuilt_qt_keeps_source_fallback_available(self):
        host = self.root / 'cache/qt-mxe/6.12.0/gcc_64'
        (host / 'bin').mkdir(parents=True)
        (host / 'bin/qmake').touch()
        with patch('mxe_setup.subprocess.check_output', side_effect=['x86_64-pc-linux-gnu\n', 'wrong-version\n']):
            setup.bootstrap_native_tools(self.root, self.root / 'cache')
        self.assertFalse((self.root / 'usr/x86_64-pc-linux-gnu/installed/qt6-qtbase').exists())
