#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

QEMU_REPOSITORY=https://github.com/espressif/qemu.git
QEMU_COMMIT=40edccac415693c5130f91c01d84176ae6008566

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
WORK_ROOT=${SIMULATOR_QEMU_WORK_ROOT:-"$PROJECT_ROOT/.cache/qemu"}
SOURCE_DIR="$WORK_ROOT/source"
BUILD_DIR="$SOURCE_DIR/build"

for command_name in git python3 ninja pkg-config cc; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "missing required command: $command_name" >&2
        exit 1
    fi
done

for package_name in glib-2.0 pixman-1 libgcrypt; do
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

ACTUAL_COMMIT=$(git -C "$SOURCE_DIR" rev-parse HEAD)
if [ "$ACTUAL_COMMIT" != "$QEMU_COMMIT" ]; then
    echo "QEMU commit mismatch: expected $QEMU_COMMIT, got $ACTUAL_COMMIT" >&2
    exit 1
fi

for patch_file in "$PROJECT_ROOT"/emulator/qemu/patches/*.patch; do
    if git -C "$SOURCE_DIR" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
        echo "QEMU patch is already applied: $patch_file"
    else
        git -C "$SOURCE_DIR" apply --check "$patch_file"
        git -C "$SOURCE_DIR" apply "$patch_file"
    fi
done

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
    --disable-slirp

ninja -C "$BUILD_DIR" qemu-system-xtensa

echo "built $BUILD_DIR/qemu-system-xtensa"
echo "run workers with networking disabled and an operator-supplied ESP32-S3 ROM path"
