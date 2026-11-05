#!/bin/bash
set -euo pipefail
export PATH="/opt/mxe/usr/bin:$PATH"
triplet=x86_64-w64-mingw32.shared
git config --global --add safe.directory /opt/mxe
if [[ ! -d /opt/mxe/.git ]]; then
 git clone https://github.com/mxe/mxe.git /opt/mxe
fi
exec 9>/opt/mxe/.build.lock
flock 9
git -C /opt/mxe checkout --force aa79465f3b05227bc568ae0dc12fe22c58c11cc4
# Limit FFmpeg to the emulator's decoders; avoid unrelated encoders and codec libraries.
cp /scripts/ffmpeg.mk /opt/mxe/src/ffmpeg.mk
# The frontend uses Widgets Charts, so Qt Quick and its native toolchain are unnecessary.
sed -i 's/ qt6-qtdeclarative//g' /opt/mxe/src/qt/qt6/qt6-qtcharts.mk
make -C /opt/mxe MXE_TARGETS="$triplet" JOBS="${BUILD_JOBS:-3}" \
 qt6-qtbase qt6-qtcharts boost openssl opus libusb ffmpeg
