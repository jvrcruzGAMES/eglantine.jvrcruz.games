"""Download and validate official prebuilt MinGW Qt libraries before selecting them."""
from pathlib import Path
import os
import subprocess
import tempfile

VERSION = '6.8.3'


def ensure_qt(cache):
    target = cache / f'qt-windows/{VERSION}/mingw_64'
    host = cache / f'qt/{VERSION}/gcc_64'
    required = ['lib/cmake/Qt6/Qt6Config.cmake', 'lib/cmake/Qt6Charts/Qt6ChartsConfig.cmake',
                'bin/Qt6Core.dll', 'plugins/platforms/qwindows.dll']
    if not all((target / name).is_file() for name in required):
        subprocess.run(['aqt', 'install-qt', 'windows', 'desktop', VERSION, 'win64_mingw',
                        '-m', 'qtcharts', '-O', str(cache / 'qt-windows'), '--archives', 'qtbase'], check=True)
    if not (host / 'bin/qmake').is_file():
        subprocess.run(['aqt', 'install-qt', 'linux', 'desktop', VERSION, 'linux_gcc_64',
                        '-O', str(cache / 'qt'), '--archives', 'qtbase', 'icu'], check=True)
    if not all((target / name).is_file() for name in required):
        raise RuntimeError('The prebuilt Windows Qt kit is incomplete')
    version = subprocess.check_output([str(host / 'bin/qmake'), '-query', 'QT_VERSION'], text=True).strip()
    if version != VERSION:
        raise RuntimeError(f'Expected host Qt {VERSION}, got {version}')
    return target, host


def probe(target, host, scripts, work):
    env = dict(os.environ, EGLANTINE_QT_HOST=str(host), EGLANTINE_QT_TARGET=str(target))
    with tempfile.TemporaryDirectory(prefix='qt-prebuilt-probe-', dir=work) as directory:
        root = Path(directory)
        (root / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.22)
project(prebuilt_probe LANGUAGES CXX)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 6.8.3 EXACT REQUIRED COMPONENTS Widgets Charts)
add_executable(probe main.cpp probe.h)
target_link_libraries(probe PRIVATE Qt6::Widgets Qt6::Charts)
''')
        (root / 'probe.h').write_text('#include <QObject>\nclass Probe : public QObject {\n    Q_OBJECT\n};\n')
        (root / 'main.cpp').write_text('''#include "probe.h"
#include <QApplication>
#include <QtCharts/QChart>
#include <QString>
#include <string>
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    Probe object;
    QChart chart;
    chart.setTitle(QString::fromStdString(std::string("MinGW Qt probe")));
    return chart.title().isEmpty();
}
''')
        subprocess.run(['x86_64-w64-mingw32.shared-cmake', '-S', str(root), '-B', str(root / 'build'),
                        '-G', 'Ninja', f'-DCMAKE_TOOLCHAIN_FILE={scripts}/windows-toolchain.cmake',
                        f'-DQt6_DIR={target}/lib/cmake/Qt6', f'-DCMAKE_PREFIX_PATH={target}'], check=True, env=env)
        subprocess.run(['cmake', '--build', str(root / 'build')], check=True, env=env)
        subprocess.run(['python3', str(scripts / 'windows_deps.py'), str(root / 'build'),
                        '/opt/mxe/usr/x86_64-w64-mingw32.shared', str(target)], check=True, env=env)
        if env.get('WINDOWS_QT_PROBE_RUNNER'):
            subprocess.run([env['WINDOWS_QT_PROBE_RUNNER'], str(root / 'build/probe.exe'), '-platform', 'offscreen'], check=True, env=env, timeout=120)


def select(cache, scripts, work):
    try:
        target, host = ensure_qt(cache)
        probe(target, host, scripts, work)
    except (subprocess.CalledProcessError, OSError, RuntimeError) as exc:
        print(f'Prebuilt Windows Qt unavailable or incompatible ({exc}); using source-built Qt.', flush=True)
        return False
    print(f'Using official prebuilt Windows MinGW Qt {VERSION} (Widgets and Charts); compile/link and DLL checks passed.', flush=True)
    return True


if __name__ == '__main__':
    raise SystemExit(0 if select(Path('/cache'), Path('/scripts'), Path('/work')) else 1)
