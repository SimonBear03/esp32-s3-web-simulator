#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

PIO_COMMAND=${PIO_COMMAND:-pio}
PLATFORMIO_ROOT=${PLATFORMIO_CORE_DIR:-"${HOME:?}/.platformio"}
BUILD_DIRECTORY=.pio/build/qemu-esp32s3
ESPTOOL="$PLATFORMIO_ROOT/packages/tool-esptoolpy/esptool.py"
BOOT_APP0="$PLATFORMIO_ROOT/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"
OUTPUT="$BUILD_DIRECTORY/firmware-merged.bin"

"$PIO_COMMAND" run
python3 "$ESPTOOL" --chip esp32s3 merge_bin \
    --output "$OUTPUT" \
    --flash_mode dio \
    --flash_freq 80m \
    --flash_size 8MB \
    0x0000 "$BUILD_DIRECTORY/bootloader.bin" \
    0x8000 "$BUILD_DIRECTORY/partitions.bin" \
    0xe000 "$BOOT_APP0" \
    0x20000 "$BUILD_DIRECTORY/firmware.bin"

echo "built $OUTPUT"
