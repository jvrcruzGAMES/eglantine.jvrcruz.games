#!/usr/bin/env python3
"""Reuse a CMake build tree, retrying once with a fresh tree on failure."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def build(build_dir, configure):
    build_dir = Path(build_dir).absolute()
    if build_dir.is_symlink() or build_dir.parent == build_dir or build_dir.name != 'linux':
        raise ValueError('Expected a dedicated linux build directory')
    had_state = build_dir.exists() and any(build_dir.iterdir())

    def attempt():
        subprocess.run(configure, check=True)
        subprocess.run(['cmake', '--build', str(build_dir), '--target', 'yuzu', 'yuzu-cmd'], check=True)

    print('Build mode: incremental' if had_state else 'Build mode: full (first build)', flush=True)
    try:
        attempt()
    except subprocess.CalledProcessError:
        if not had_state:
            raise
        print('Incremental configure/build failed; retrying once with a clean build tree.', flush=True)
        # Only the platform CMake tree is removed. Source, CPM and ccache stay intact.
        shutil.rmtree(build_dir)
        attempt()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', required=True)
    parser.add_argument('configure', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    configure = args.configure[1:] if args.configure[:1] == ['--'] else args.configure
    if not configure:
        parser.error('a configure command is required after --')
    try:
        build(args.build_dir, configure)
    except subprocess.CalledProcessError as exc:
        return exc.returncode
    return 0


if __name__ == '__main__':
    sys.exit(main())
