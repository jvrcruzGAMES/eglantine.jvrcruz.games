"""Prepare cached MXE recipes without invalidating completed packages."""
from pathlib import Path
import os
import subprocess


def write_changed(path, content):
    if not path.exists() or path.read_bytes() != content:
        path.write_bytes(content)


def prepare(root, scripts):
    installed = root / 'usr/x86_64-w64-mingw32.shared/installed'
    for name in ('ffmpeg', 'dav1d'):
        write_changed(root / f'src/{name}.mk', (scripts / f'{name}.mk').read_bytes())
    charts = root / 'src/qt/qt6/qt6-qtcharts.mk'
    write_changed(charts, charts.read_bytes().replace(b' qt6-qtdeclarative', b''))
    # Preserve already compiled Qt and Boost on existing servers. Slim only unfinished packages.
    if not (installed / 'qt6-qtbase').exists():
        write_changed(root / 'src/qt/qt6/qt6-qtbase.mk', (scripts / 'qt6-qtbase-minimal.mk').read_bytes())
    if not (installed / 'boost').exists():
        boost = root / 'src/boost.mk'
        choices = b'--with-filesystem --with-context --with-fiber --with-container --with-process --with-serialization --with-thread --with-chrono --with-atomic'
        write_changed(boost, boost.read_bytes().replace(b'--without-mpi', choices).replace(b'--without-python', b''))


def bootstrap_native_tools(root, cache):
    native = subprocess.check_output([str(root / 'ext/config.guess')], text=True).strip()
    prefix = root / 'usr' / native
    installed = prefix / 'installed'
    installed.mkdir(parents=True, exist_ok=True)
    if not (installed / 'cmake').exists():
        (prefix / 'bin').mkdir(parents=True, exist_ok=True)
        for name in ('cmake', 'ctest', 'cpack'):
            target = prefix / 'bin' / name
            if not target.exists(): target.symlink_to('/usr/local/bin/' + name)
        (installed / 'cmake').touch()
        print('Using preinstalled native CMake; skipping CMake source compilation.', flush=True)
    if not (installed / 'qt6-qtbase').exists() and os.environ.get('MXE_SKIP_QT', '0') != '1' and os.environ.get('MXE_PREBUILT_HOST_QT', '1') != '0':
        host = cache / 'qt-mxe/6.12.0/gcc_64'
        if not (host / 'bin/qmake').exists():
            try:
                subprocess.run(['aqt', 'install-qt', 'linux', 'desktop', '6.12.0', 'linux_gcc_64', '-O', str(cache / 'qt-mxe'), '--archives', 'qtbase', 'icu'], check=True)
            except subprocess.CalledProcessError:
                print('Prebuilt host Qt download failed; falling back to the native Qt source build.', flush=True)
                return
        try:
            version = subprocess.check_output([str(host / 'bin/qmake'), '-query', 'QT_VERSION'], text=True).strip()
            if version != '6.12.0':
                raise ValueError(f'Unexpected host Qt version: {version}')
        except (subprocess.CalledProcessError, OSError, ValueError) as exc:
            print(f'Prebuilt host Qt is unusable ({exc}); falling back to native source build.', flush=True)
            return
        dest = prefix / 'qt6'
        # A previous failed native build may have left a partial install. Keep it for diagnosis.
        if dest.exists() and not dest.is_symlink():
            backup = prefix / 'qt6.partial'
            if backup.exists():
                print('Partial native Qt backup already exists; using MXE source fallback.', flush=True)
                return
            dest.rename(backup)
        if not dest.exists(): dest.symlink_to(host)
        (installed / 'qt6-qtbase').touch()
        print('Using official prebuilt Qt 6.12.0 host tools; skipping native Qt compilation.', flush=True)


if __name__ == '__main__':
    root = Path('/opt/mxe')
    prepare(root, Path('/scripts'))
    bootstrap_native_tools(root, Path('/cache'))
