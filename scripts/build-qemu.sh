#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

QEMU_REPOSITORY=https://github.com/espressif/qemu.git
QEMU_COMMIT=40edccac415693c5130f91c01d84176ae6008566

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WORK_ROOT=${SIMULATOR_QEMU_WORK_ROOT:-"$PROJECT_ROOT/.cache/qemu"}
SOURCE_DIR="$WORK_ROOT/source"
BUILD_DIR="$SOURCE_DIR/build"
PATCH_FILE="$PROJECT_ROOT/emulator/qemu/patches/0001-m25p80-support-gigadevice-qe-status.patch"

for command_name in git python3 ninja pkg-config cc; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "missing required command: $command_name" >&2
        exit 1
    fi
done

for package_name in glib-2.0 pixman-1 libgcrypt slirp; do
    if ! pkg-config --exists "$package_name"; then
        echo "missing pkg-config dependency: $package_name" >&2
        exit 1
    fi
done

mkdir -p "$WORK_ROOT"

if [ ! -d "$SOURCE_DIR/.git" ]; then
    git clone --filter=blob:none --no-checkout "$QEMU_REPOSITORY" "$SOURCE_DIR"
fi

git -C "$SOURCE_DIR" fetch --depth=1 origin "$QEMU_COMMIT"
git -C "$SOURCE_DIR" checkout --detach "$QEMU_COMMIT"
git -C "$SOURCE_DIR" submodule update --init --recursive --depth=1

ACTUAL_COMMIT=$(git -C "$SOURCE_DIR" rev-parse HEAD)
if [ "$ACTUAL_COMMIT" != "$QEMU_COMMIT" ]; then
    echo "QEMU commit mismatch: expected $QEMU_COMMIT, got $ACTUAL_COMMIT" >&2
    exit 1
fi

if git -C "$SOURCE_DIR" apply --reverse --check "$PATCH_FILE" >/dev/null 2>&1; then
    echo "QEMU compatibility patch is already applied"
else
    git -C "$SOURCE_DIR" apply --check "$PATCH_FILE"
    git -C "$SOURCE_DIR" apply "$PATCH_FILE"
fi

cd "$SOURCE_DIR"
./configure \
    --target-list=xtensa-softmmu \
    --disable-werror \
    --disable-curses \
    --disable-docs \
    --disable-gtk \
    --disable-opengl \
    --disable-sdl \
    --disable-virglrenderer \
    --disable-vnc \
    --enable-slirp \
    --with-git-submodules=ignore

ninja -C "$BUILD_DIR" qemu-system-xtensa

echo "built $BUILD_DIR/qemu-system-xtensa"
echo "run workers with networking disabled and an operator-supplied ESP32-S3 ROM path"
