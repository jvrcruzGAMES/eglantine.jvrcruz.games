#!/bin/bash
set -euo pipefail
export PATH="/opt/mxe/usr/bin:$PATH"
triplet=x86_64-w64-mingw32.shared
pin=aa79465f3b05227bc568ae0dc12fe22c58c11cc4
git config --global --add safe.directory /opt/mxe
if [[ ! -d /opt/mxe/.git ]]; then
 git clone https://github.com/mxe/mxe.git /opt/mxe
fi
exec 9>/opt/mxe/.build.lock
flock 9
if [[ $(git -C /opt/mxe rev-parse HEAD) != "$pin" ]]; then
 git -C /opt/mxe checkout --force "$pin"
fi
python3 /scripts/mxe_setup.py
# File contents, not timestamps, control when our setup changes invalidate readiness.
fingerprint=$(sha256sum /scripts/mxe.sh /scripts/mxe_setup.py /scripts/ffmpeg.mk /scripts/dav1d.mk /scripts/qt6-qtbase-minimal.mk | sha256sum | cut -d' ' -f1)
ready=/opt/mxe/.eglantine-toolchain-ready
packages=(qt6-qtbase qt6-qtcharts boost openssl opus libusb1 ffmpeg dav1d)
complete=true
for package in "${packages[@]}"; do
 [[ -f /opt/mxe/usr/$triplet/installed/$package ]] || complete=false
done
if [[ "$complete" = true && -f "$ready" && $(cat "$ready") = "$fingerprint" && -x /opt/mxe/usr/bin/$triplet-g++ && -x /opt/mxe/usr/bin/$triplet-cmake ]]; then
 echo 'Reusing completed MinGW/Qt toolchain; no bootstrap work needed.'
 exit 0
fi
make -C /opt/mxe MXE_TARGETS="$triplet" JOBS="${BUILD_JOBS:-3}" "${packages[@]}"
printf '%s\n' "$fingerprint" > "$ready"
