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
GigaDevice behavior. `patches/0002-esp32s3-i2c-cardputer-tca8418.patch`
maps the ESP32-S3 I2C controllers, adds the S3 command encoding, introduces
explicit `cardputer-adv` and `sticks3` machine profiles, and attaches an
original TCA8418 keyboard model to the Cardputer ADV profile. Both patches are
GPL-2.0-only and covered by real-firmware conformance tests.

`patches/0003-esp32s3-gpio-input-interrupts.patch` adds the ESP32-S3 GPIO
input/output/status register subset, edge and level interrupt behavior, and the
GPIO interrupt-matrix route. It connects the TCA8418 active-low interrupt to
Cardputer ADV GPIO 11, allowing the normal ESP-IDF ISR path to consume keys
without firmware polling.

`patches/0004-esp32s3-gpspi-st7789.patch` adds the ESP32-S3 CPU-FIFO SPI2/SPI3
path, transaction-done status and interrupts, and an original ST7789 model.
The Cardputer ADV profile exposes a cropped 240x135 framebuffer and the StickS3
profile exposes 135x240. QMP `screendump` captures the physical board display;
the generic 800x600 helper is retained only for the profile-free machine.

`patches/0005-esp32s3-sticks3-octal-psram-qio.patch` selects the existing octal
PSRAM command model for the StickS3 profile and adapts ESP32-S3 quad-I/O read
dummy cycles to QEMU's serialized GigaDevice flash model. It also fixes the SPI
transfer-buffer index checks. The owned StickS3 fixture validates the real
`qio_opi` configuration with exact 8 MiB PSRAM and NVS readback across reset.

`patches/0006-esp32s3-sticks3-buttons-imu-power.patch` adds active-low
StickS3 buttons on GPIO 11/12, a behavioral BMI270 at I2C address `0x68`, and
a behavioral M5PM1 at `0x6e`. Dedicated QOM properties let the private worker
inject button transitions, physical-unit IMU samples, battery voltage, input
voltage, and charging state deterministically. These values reach firmware
through the normal GPIO and I2C paths; the model does not claim analog
electrical, noise, calibration, or brownout fidelity.

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
gitignored `.cache/qemu/` directory, applies the tracked patches in order, and builds only
`qemu-system-xtensa`. It does not download or commit user firmware.

Workers select the board model with `-M esp32s3,board-profile=cardputer-adv`
or `-M esp32s3,board-profile=sticks3`. The service translates its stable input
protocol to private QMP keyboard and QOM operations; browser clients never need
QEMU key codes or object paths.
The service captures the board framebuffer through QMP and validates QEMU's P6
RGB output before exposing it through the engine-neutral web protocol.

## ROM and networking policy

An ESP32-S3 boot ROM is required at runtime. It is not distributed by this
repository; the operator must obtain it from Espressif and review the applicable
terms. Production workers must invoke QEMU with guest networking disabled and
must also be isolated at the operating-system/container boundary.
