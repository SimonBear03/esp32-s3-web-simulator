#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$PROJECT_ROOT"

find scripts -type f -name '*.sh' -exec sh -n {} \;
python3 -m json.tool emulator/qemu/version.json >/dev/null
git diff --check
git diff --cached --check

for required_file in \
    LICENSE \
    THIRD_PARTY.md \
    docs/licensing.md \
    emulator/qemu/version.json \
    emulator/qemu/patches/0001-m25p80-support-gigadevice-qe-status.patch \
    emulator/qemu/patches/0002-esp32s3-i2c-cardputer-tca8418.patch \
    emulator/qemu/patches/0003-esp32s3-gpio-input-interrupts.patch \
    emulator/qemu/patches/0004-esp32s3-gpspi-st7789.patch
do
    if [ ! -s "$required_file" ]; then
        echo "missing required foundation file: $required_file" >&2
        exit 1
    fi
done

tracked_runtime_artifacts=$(
    git ls-files | grep -E '\.(bin|elf|map|qcow2|nvs|log)$' || true
)
if [ -n "$tracked_runtime_artifacts" ]; then
    echo "runtime artifacts must not be tracked:" >&2
    echo "$tracked_runtime_artifacts" >&2
    exit 1
fi

echo "foundation checks passed"
