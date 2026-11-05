#!/bin/bash
source /scripts/common.sh
export PATH="/opt/mxe/usr/bin:$PATH"
triplet=x86_64-w64-mingw32.shared
bash /scripts/mxe.sh
python3 /scripts/incremental_build.py --build-dir /work/windows -- \
 "$triplet-cmake" -S . -B /work/windows -G Ninja "${common_flags[@]}" \
 -DCMAKE_PREFIX_PATH="/opt/mxe/usr/$triplet/qt6" \
 -DYUZU_USE_BUNDLED_FFMPEG=OFF -DFFmpeg_FORCE_SYSTEM=ON \
 -DFFmpeg_CROSS_PREFIX="/opt/mxe/usr/bin/$triplet-"
python3 /scripts/windows_deps.py /work/windows/bin "/opt/mxe/usr/$triplet"
cp /source/LICENSE.txt /work/windows/bin/LICENSE.txt
cd /work/windows/bin
"$triplet-strip" eglantine.exe eden-cli.exe
zip -qr /out/Eglantine-Windows-x86_64.zip .
