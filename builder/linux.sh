#!/bin/bash
source /scripts/common.sh
export PACKAGE_NAME="${PACKAGE_NAME:-eglantine}"
if [[ "$PACKAGE_NAME" = eglantine-nightly ]]; then
 appimage=Eglantine-nightly-x86_64.AppImage
 desktop=eglantine-nightly.desktop
 icon=dev.eglantine.eglantine-nightly
 channel_path=/nightly
else
 appimage=Eglantine-x86_64.AppImage
 desktop=dev.eden_emu.eden.desktop
 icon=dev.eglantine.eglantine
 channel_path=
fi
(
 flock 8
 # Windows needs only native Qt tools; Linux also needs the Charts libraries.
 if [[ ! -x /cache/qt/6.8.3/gcc_64/bin/qmake || ! -f /cache/qt/6.8.3/gcc_64/lib/cmake/Qt6Charts/Qt6ChartsConfig.cmake ]]; then
  aqt install-qt linux desktop 6.8.3 linux_gcc_64 -m qtcharts -O /cache/qt
 fi
) 8>/cache/.qt-download.lock
export QT_ROOT_DIR=/cache/qt/6.8.3/gcc_64
export PATH="$QT_ROOT_DIR/bin:$PATH"
export LD_LIBRARY_PATH="$QT_ROOT_DIR/lib:${LD_LIBRARY_PATH:-}"
python3 /scripts/incremental_build.py --build-dir /work/linux -- \
 cmake -S . -B /work/linux -G Ninja "${common_flags[@]}" -DCMAKE_PREFIX_PATH="$QT_ROOT_DIR"
strip /work/linux/bin/eglantine /work/linux/bin/eden-cli
mkdir -p /cache/tools /out
for name in linuxdeploy linuxdeploy-plugin-qt; do
 if [[ ! -s /cache/tools/$name.AppImage ]]; then
  curl --retry 3 -fL "https://github.com/linuxdeploy/$name/releases/download/continuous/$name-x86_64.AppImage" -o "/cache/tools/$name.AppImage"
  chmod +x "/cache/tools/$name.AppImage"
 fi
done
python3 /scripts/package_linux.py desktop
export APPIMAGE_EXTRACT_AND_RUN=1 QMAKE="$QT_ROOT_DIR/bin/qmake"
export LDAI_VERSION="$PACKAGE_VERSION" ARCH=x86_64
export UPDATE_INFORMATION="zsync|$PUBLIC_URL$channel_path/updates/$appimage.zsync"
export LDAI_UPDATE_INFORMATION="$UPDATE_INFORMATION"
export LDAI_OUTPUT="/out/$appimage" OUTPUT="/out/$appimage"
export PATH="/cache/tools:$PATH"
ln -sf /cache/tools/linuxdeploy-plugin-qt.AppImage /cache/tools/linuxdeploy-plugin-qt
cd /work
rm -rf AppDir
/cache/tools/linuxdeploy.AppImage --appdir AppDir \
 --executable /work/linux/bin/eglantine --executable /work/linux/bin/eden-cli \
 --desktop-file "/work/$desktop" \
 --icon-file "/work/$icon.png" --plugin qt --output appimage
test -s "$OUTPUT"
# Generate explicitly with the stable download name and URL.
cd /out
zsyncmake -u "$PUBLIC_URL$channel_path/updates/$appimage" "$appimage"
python3 /scripts/package_linux.py deb
