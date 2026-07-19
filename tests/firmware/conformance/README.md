# ESP32-S3 base conformance firmware

This simulator-owned fixture is the release gate for the base ESP32-S3 worker.
It emits a stable UART contract for boot, flash capacity, heap, NVS persistence,
timers, heartbeat continuity, byte-stream input, software reset, ESP32-S3 I2C,
TCA8418 key-event delivery, ESP32-S3 SPI3, and ST7789 framebuffer output.
The StickS3 build also gates GPIO buttons, BMI270 samples, M5PM1 power state,
and octal PSRAM.

## Build

Install PlatformIO Core, then run from this directory:

```sh
./build-merged.sh
```

The default Cardputer ADV merged image is
`.pio/build/qemu-esp32s3/firmware-merged.bin`. Build the StickS3 variant with
`PIO_ENV=qemu-sticks3 ./build-merged.sh`; it is written under
`.pio/build/qemu-sticks3/`. PlatformIO's generated files are ignored and must
not be committed.

The environment pins PlatformIO's Espressif32 platform to 6.12.0 (Arduino-ESP32
2.0.17). The Cardputer ADV image uses DIO flash at 80 MHz; StickS3 uses its real
QIO-flash plus octal-PSRAM mode. Both use UART0 rather than USB CDC.

## UART contract

Successful base conformance requires:

- `SIM:BOOT version=1 profile=cardputer-adv` or `profile=sticks3`;
- `SIM:FLASH bytes=8388608`;
- exact four-byte NVS write/readback equality and a boot count increasing from
  1 to 2 after reset on the same flash;
- `SIM:READY` followed by at least three ordered `SIM:HEARTBEAT` lines;
- QMP pause halting heartbeats, framebuffer capture while paused, resume
  restoring heartbeats, and QMP reset preserving the private flash image;
- `ping\n` producing `SIM:PONG`;
- TCA8418 configuration at address `0x34` over the Cardputer ADV's I2C1
  controller, with QMP-injected `W`, `A`, `S`, `D`, and Enter press/release
  events reaching the firmware through nINT, GPIO 11, and the ESP-IDF ISR
  without polling; the exact FIFO pairs are `0x8c/0x0c`, `0x8d/0x0d`,
  `0x91/0x11`, `0x97/0x17`, and `0xc3/0x43`;
- Cardputer ADV LEDC channel 7 setup on GPIO 38 at 256 Hz with an 8-bit duty of
  110, exercising the display-backlight initialization path used by M5GFX;
- a CPU-FIFO SPI3 transaction path that initializes the Cardputer ADV ST7789,
  enables the panel's normal inversion mode, renders a deterministic red/blue
  240x135 framebuffer without photographic color inversion, and emits
  `SIM:DISPLAY controller=st7789 width=240 height=135 pattern=red-blue`;
- the corresponding StickS3 pins, 135x240 crop, and exact framebuffer
  assertions when the StickS3 fixture is selected;
- StickS3 octal-PSRAM initialization, an exact 8 MiB capacity assertion, and a
  deterministic 4 KiB allocation/write/read/free test;
- StickS3 button A/B press and release transitions reaching active-low GPIO
  11/12;
- BMI270 identity `0x24` at I2C address `0x68`, a stationary default sample,
  and an injected 1 g X / 250 dps Z sample read back as deterministic raw data;
- M5PM1 identity at I2C address `0x6e`, default battery/VIN/charging telemetry,
  and an injected battery-only, charging-off state read back through registers;
- `reset\n` producing another boot sequence without replacing the flash image.

Later board models extend this contract rather than weakening it.

From the repository root, exercise the built image through the real session
service with:

```sh
make base-conformance \
  QEMU=/path/to/qemu-system-xtensa \
  ROMS=/path/to/qemu/roms \
  FIRMWARE=tests/firmware/conformance/.pio/build/qemu-esp32s3/firmware-merged.bin \
  BOARD_ID=cardputer-adv
```

Add `--no-qmp` directly to `scripts/run-base-conformance.py` only in a test
sandbox that denies Unix-domain sockets. Production conformance must include
QMP.
