# Espressif QEMU integration

The simulator pins Espressif QEMU `esp-develop-9.2.2-20260417` at immutable
commit `40edccac415693c5130f91c01d84176ae6008566`.

## Why a source build is required

The upstream ESP32-S3 machine selects a GigaDevice flash model for an 8 MiB
image. ESP-IDF 4.4 configures that part's quad-enable bit through status
register 2. Upstream QEMU 9.2.2 models this command path for Winbond but not
GigaDevice, causing default-flash initialization to fail before application
startup.

`patches/0001-m25p80-support-gigadevice-qe-status.patch` adds the equivalent
GigaDevice behavior. The patch is intentionally narrow and must stay covered by
a real-firmware boot test.

## Build

On Ubuntu 24.04, install the native build dependencies:

```sh
sudo apt-get install \
  build-essential git ninja-build pkg-config python3-venv \
  libglib2.0-dev libpixman-1-dev libgcrypt20-dev libslirp-dev
```

Then run:

```sh
scripts/build-qemu.sh
```

The script clones the immutable commit and its pinned submodules into the
gitignored `.cache/qemu/` directory, applies the tracked patch, and builds only
`qemu-system-xtensa`. It does not download or commit user firmware.

## ROM and networking policy

An ESP32-S3 boot ROM is required at runtime. It is not distributed by this
repository; the operator must obtain it from Espressif and review the applicable
terms. Production workers must invoke QEMU with guest networking disabled and
must also be isolated at the operating-system/container boundary.
