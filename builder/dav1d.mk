# SPDX-License-Identifier: MIT
# Minimal AV1 decoder package for the pinned MXE revision, which has no dav1d recipe.
PKG := dav1d
$(PKG)_VERSION := 1.5.1
$(PKG)_CHECKSUM := 401813f1f89fa8fd4295805aa5284d9aed9bc7fc1fdbe554af4292f64cbabe21
$(PKG)_SUBDIR := dav1d-$($(PKG)_VERSION)
$(PKG)_FILE := dav1d-$($(PKG)_VERSION).tar.xz
$(PKG)_URL := https://download.videolan.org/pub/videolan/dav1d/$($(PKG)_VERSION)/$($(PKG)_FILE)
$(PKG)_DEPS := cc meson-wrapper $(BUILD)~nasm

define $(PKG)_BUILD
    '$(MXE_MESON_WRAPPER)' $(MXE_MESON_OPTS) \
        -Denable_tools=false -Denable_tests=false -Denable_examples=false \
        -Denable_docs=false $(PKG_MESON_OPTS) '$(BUILD_DIR)' '$(SOURCE_DIR)'
    '$(MXE_NINJA)' -C '$(BUILD_DIR)' -j '$(JOBS)'
    '$(MXE_NINJA)' -C '$(BUILD_DIR)' install
endef
