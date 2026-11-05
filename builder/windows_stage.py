"""Create a clean package from application outputs, excluding old Qt deployments."""
from pathlib import Path
import shutil
import sys


def stage(source, target):
    if target.name != 'windows-package' or target.is_symlink():
        raise ValueError('Expected the dedicated windows-package directory')
    if target.exists(): shutil.rmtree(target)
    target.mkdir(parents=True)
    runtimes = {'libstdc++-6.dll', 'libgcc_s_seh-1.dll', 'libwinpthread-1.dll'}
    for file in source.iterdir():
        if file.is_file() and file.suffix.lower() in ('.exe', '.dll', '.txt', '.json') and not file.name.lower().startswith('qt6') and file.name.lower() not in runtimes:
            shutil.copy2(file, target / file.name)


if __name__ == '__main__': stage(Path(sys.argv[1]), Path(sys.argv[2]))
