#!/bin/bash
source /scripts/common.sh
export PATH="/opt/mxe/usr/bin:$PATH"
triplet=x86_64-w64-mingw32.shared
prebuilt=false
if [[ "${WINDOWS_PREBUILT_LIBS:-1}" != 0 ]]; then
 MXE_SKIP_QT=1 bash /scripts/mxe.sh
 if python3 /scripts/prebuilt_windows.py; then
  prebuilt=true
  export EGLANTINE_QT_HOST=/cache/qt/6.8.3/gcc_64
  qt=/cache/qt-windows/6.8.3/mingw_64
  export EGLANTINE_QT_TARGET="$qt"
 fi
fi
if [[ "$prebuilt" = false ]]; then
 bash /scripts/mxe.sh
 qt="/opt/mxe/usr/$triplet/qt6"
 unset EGLANTINE_QT_HOST EGLANTINE_QT_TARGET
fi
build_application() {
 python3 /scripts/incremental_build.py --build-dir /work/windows -- \
  "$triplet-cmake" -S . -B /work/windows -G Ninja "${common_flags[@]}" \
  -DCMAKE_TOOLCHAIN_FILE=/scripts/windows-toolchain.cmake \
  -DQt6_DIR="$qt/lib/cmake/Qt6" -DCMAKE_PREFIX_PATH="$qt" \
  -DYUZU_USE_BUNDLED_FFMPEG=OFF -DFFmpeg_FORCE_SYSTEM=ON \
  -DFFmpeg_CROSS_PREFIX="/opt/mxe/usr/bin/$triplet-"
}
# The helper returns the configure/build process status.
if (build_application); then
 :
elif [[ "$prebuilt" = true ]]; then
 echo 'Application build with prebuilt Qt failed; retrying with source-built Qt.'
 unset EGLANTINE_QT_HOST EGLANTINE_QT_TARGET
 bash /scripts/mxe.sh
 qt="/opt/mxe/usr/$triplet/qt6"
 build_application
else
 exit 1
fi
# Package into a separate clean directory so old Qt DLLs/plugins cannot leak across kit changes.
python3 /scripts/windows_stage.py /work/windows/bin /work/windows-package
python3 /scripts/windows_deps.py /work/windows-package "/opt/mxe/usr/$triplet" "$qt"
cp /source/LICENSE.txt /work/windows-package/LICENSE.txt
cd /work/windows-package
"$triplet-strip" eglantine.exe eden-cli.exe
python3 /scripts/windows_installer.py
