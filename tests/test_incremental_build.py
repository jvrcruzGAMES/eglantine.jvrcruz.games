import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('incremental_build', Path(__file__).resolve().parents[1] / 'builder/incremental_build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class IncrementalBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.work = self.root / 'linux'
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        (self.cache / 'preserve').write_text('cached dependency')
        (self.source / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.16)
project(incremental_test C)
if(NOT EXISTS "${CMAKE_BINARY_DIR}/generated.h")
  file(WRITE "${CMAKE_BINARY_DIR}/generated.h" "#define RESULT 0\\n")
endif()
add_executable(yuzu main.c)
target_include_directories(yuzu PRIVATE "${CMAKE_BINARY_DIR}")
add_custom_target(yuzu-cmd DEPENDS yuzu)
''')
        (self.source / 'main.c').write_text('#include "generated.h"\nint main(void) { return RESULT; }\n')
        self.configure = ['cmake', '-S', str(self.source), '-B', str(self.work), '-G', 'Ninja']

    def test_unchanged_build_reuses_objects(self):
        builder.build(self.work, self.configure)
        obj = next(self.work.rglob('*.o'))
        original = obj.stat().st_mtime_ns
        builder.build(self.work, self.configure)
        self.assertEqual(obj.stat().st_mtime_ns, original)

    def test_stale_configuration_falls_back_to_clean_build(self):
        builder.build(self.work, self.configure)
        cache = self.work / 'CMakeCache.txt'
        cache.write_text(cache.read_text().replace(str(self.source), str(self.root / 'old-source')))
        builder.build(self.work, self.configure)
        self.assertIn(str(self.source), cache.read_text())
        self.assertEqual((self.cache / 'preserve').read_text(), 'cached dependency')

    def test_stale_generated_header_falls_back_after_compile_failure(self):
        builder.build(self.work, self.configure)
        (self.work / 'generated.h').write_text('#error stale generated header\n')
        builder.build(self.work, self.configure)
        self.assertEqual(subprocess.run([str(self.work / 'yuzu')]).returncode, 0)
        self.assertEqual((self.cache / 'preserve').read_text(), 'cached dependency')

    def test_clean_failure_is_propagated(self):
        builder.build(self.work, self.configure)
        (self.source / 'main.c').write_text('#error broken upstream source\n')
        with self.assertRaises(subprocess.CalledProcessError):
            builder.build(self.work, self.configure)
        self.assertEqual((self.cache / 'preserve').read_text(), 'cached dependency')


if __name__ == '__main__': unittest.main()
