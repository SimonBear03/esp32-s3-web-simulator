#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DOCKER_CLIENT=${SIMULATOR_ROOTLESS_DOCKER:-/usr/bin/docker}
DOCKER_HOST_VALUE=${SIMULATOR_ROOTLESS_DOCKER_HOST:?set the dedicated rootless Docker socket}
BUILD_IMAGE=${SIMULATOR_BUILD_IMAGE:?set a digest-pinned build image}
RUNTIME_IMAGE=${SIMULATOR_RUNTIME_IMAGE:?set a digest-pinned runtime image}
ROM_PATH=${SIMULATOR_ESP32S3_ROM:?set the operator-supplied ESP32-S3 ROM path}
ROM_SHA256=${SIMULATOR_ESP32S3_ROM_SHA256:?set the reviewed ROM sha256}
IMAGE_TAG=${SIMULATOR_WORKER_IMAGE_TAG:-local/esp32-s3-worker:build}

case "$DOCKER_HOST_VALUE" in
    "unix:///run/user/$(id -u)/docker.sock") ;;
    *) echo "rootless Docker socket must belong to the current worker identity" >&2; exit 1 ;;
esac

for image in "$BUILD_IMAGE" "$RUNTIME_IMAGE"; do
    case "$image" in
        *@sha256:????????????????????????????????????????????????????????????????) ;;
        *) echo "base images must be pinned by sha256 digest" >&2; exit 1 ;;
    esac
done

if [ ! -f "$ROM_PATH" ] || [ -L "$ROM_PATH" ]; then
    echo "ESP32-S3 ROM must be a non-symlink regular file" >&2
    exit 1
fi

ACTUAL_ROM_SHA256=$(sha256sum "$ROM_PATH" | awk '{print $1}')
if [ "$ACTUAL_ROM_SHA256" != "$ROM_SHA256" ]; then
    echo "ESP32-S3 ROM digest mismatch" >&2
    exit 1
fi

ROM_CONTEXT=$(mktemp -d)
trap 'rm -rf -- "$ROM_CONTEXT"' EXIT HUP INT TERM
cp -- "$ROM_PATH" "$ROM_CONTEXT/esp32s3_rev0_rom.bin"
chmod 0444 "$ROM_CONTEXT/esp32s3_rev0_rom.bin"

"$DOCKER_CLIENT" --host "$DOCKER_HOST_VALUE" build \
    --file "$PROJECT_ROOT/emulator/qemu/container/Dockerfile" \
    --build-arg "BUILD_IMAGE=$BUILD_IMAGE" \
    --build-arg "RUNTIME_IMAGE=$RUNTIME_IMAGE" \
    --build-context "esp32rom=$ROM_CONTEXT" \
    --pull \
    --tag "$IMAGE_TAG" \
    "$PROJECT_ROOT"

IMAGE_ID=$("$DOCKER_CLIENT" --host "$DOCKER_HOST_VALUE" image inspect \
    --format '{{.Id}}' "$IMAGE_TAG")
case "$IMAGE_ID" in
    sha256:????????????????????????????????????????????????????????????????) ;;
    *) echo "Docker returned an invalid worker image ID" >&2; exit 1 ;;
esac

"$DOCKER_CLIENT" --host "$DOCKER_HOST_VALUE" run --rm \
    --network=none \
    --read-only \
    --cap-drop=ALL \
    --security-opt=no-new-privileges=true \
    "$IMAGE_ID" \
    /opt/esp32-s3/bin/qemu-system-xtensa -sandbox help >/dev/null

echo "$IMAGE_ID"
