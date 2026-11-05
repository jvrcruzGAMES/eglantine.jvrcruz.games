#!/bin/bash
source /scripts/common.sh
if [[ ! -x /cache/qt/6.8.3/gcc_64/bin/qmake ]]; then
 aqt install-qt linux desktop 6.8.3 linux_gcc_64 -m qtcharts -O /cache/qt
fi
export QT_ROOT_DIR=/cache/qt/6.8.3/gcc_64
export PATH="$QT_ROOT_DIR/bin:$PATH"
export LD_LIBRARY_PATH="$QT_ROOT_DIR/lib:${LD_LIBRARY_PATH:-}"
cmake -S . -B /work/linux -G Ninja "${common_flags[@]}" -DCMAKE_PREFIX_PATH="$QT_ROOT_DIR"
cmake --build /work/linux --target yuzu yuzu-cmd
strip /work/linux/bin/eglantine /work/linux/bin/eden-cli
mkdir -p /cache/tools /out
for name in linuxdeploy linuxdeploy-plugin-qt; do
 if [[ ! -s /cache/tools/$name.AppImage ]]; then
  curl --retry 3 -fL "https://github.com/linuxdeploy/$name/releases/download/continuous/$name-x86_64.AppImage" -o "/cache/tools/$name.AppImage"
  chmod +x "/cache/tools/$name.AppImage"
 fi
done
cp dist/Eglantine.png /work/dev.eglantine.eglantine.png
export APPIMAGE_EXTRACT_AND_RUN=1 QMAKE="$QT_ROOT_DIR/bin/qmake"
export LDAI_VERSION="$PACKAGE_VERSION" ARCH=x86_64
export UPDATE_INFORMATION="zsync|$PUBLIC_URL/updates/Eglantine-x86_64.AppImage.zsync"
export LDAI_UPDATE_INFORMATION="$UPDATE_INFORMATION"
export LDAI_OUTPUT=/out/Eglantine-x86_64.AppImage OUTPUT=/out/Eglantine-x86_64.AppImage
export PATH="/cache/tools:$PATH"
ln -sf /cache/tools/linuxdeploy-plugin-qt.AppImage /cache/tools/linuxdeploy-plugin-qt
cd /work
rm -rf AppDir
/cache/tools/linuxdeploy.AppImage --appdir AppDir \
 --executable /work/linux/bin/eglantine --executable /work/linux/bin/eden-cli \
 --desktop-file /source/dist/dev.eden_emu.eden.desktop \
 --icon-file /work/dev.eglantine.eglantine.png --plugin qt --output appimage
test -s "$OUTPUT"
# Generate explicitly with the stable download name and URL.
cd /out
zsyncmake -u "$PUBLIC_URL/updates/Eglantine-x86_64.AppImage" Eglantine-x86_64.AppImage
# Ship the same bundled userspace in /opt; AppRun establishes the Qt/library paths.
root=/work/deb
rm -rf "$root"
mkdir -p "$root/opt/eglantine" "$root/usr/bin" "$root/usr/share/applications" \
 "$root/usr/share/icons/hicolor/256x256/apps" "$root/DEBIAN" \
 "$root/usr/share/keyrings" "$root/etc/apt/sources.list.d" "$root/usr/share/doc/eglantine"
cp -a /work/AppDir/. "$root/opt/eglantine/"
cat > "$root/usr/bin/eglantine" <<'WRAPPER'
#!/bin/sh
exec /opt/eglantine/AppRun "$@"
WRAPPER
chmod 755 "$root/usr/bin/eglantine"
cp /source/dist/dev.eden_emu.eden.desktop "$root/usr/share/applications/eglantine.desktop"
cp /source/dist/Eglantine.png "$root/usr/share/icons/hicolor/256x256/apps/dev.eglantine.eglantine.png"
cp /source/LICENSE.txt "$root/usr/share/doc/eglantine/copyright"
cp /keys/eglantine-archive-keyring.gpg "$root/usr/share/keyrings/eglantine-archive-keyring.gpg"
printf 'deb [arch=amd64 signed-by=/usr/share/keyrings/eglantine-archive-keyring.gpg] %s/apt stable main\n' "$PUBLIC_URL" > "$root/etc/apt/sources.list.d/eglantine.list"
cat > "$root/DEBIAN/control" <<CONTROL
Package: eglantine
Version: $PACKAGE_VERSION
Section: games
Priority: optional
Architecture: amd64
Maintainer: Eglantine builds <builds@jvrcruz.games>
Depends: libc6 (>= 2.39), libstdc++6, libgl1, libegl1, libvulkan1, libx11-6, libxcb1, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0
Recommends: mesa-vulkan-drivers
Homepage: https://github.com/Djihads80/Eglantine
Description: Eglantine nx2 development build
 Automatically built from the nx2 branch. Includes launcher integration and APT updates.
CONTROL
cat > "$root/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null; then update-desktop-database -q /usr/share/applications || true; fi
if command -v gtk-update-icon-cache >/dev/null; then gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true; fi
POSTINST
cp "$root/DEBIAN/postinst" "$root/DEBIAN/postrm"
chmod 755 "$root/DEBIAN/postinst" "$root/DEBIAN/postrm"
dpkg-deb --root-owner-group --build "$root" /out/eglantine_amd64.deb
