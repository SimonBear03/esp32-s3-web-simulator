# ESP32-S3 base conformance firmware

This simulator-owned fixture is the release gate for the base ESP32-S3 worker.
It emits a stable UART contract for boot, flash capacity, heap, NVS persistence,
timers, heartbeat continuity, byte-stream input, software reset, ESP32-S3 I2C,
TCA8418 key-event delivery, ESP32-S3 SPI3, and ST7789 framebuffer output.

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
- TCA8418 configuration at address `0x34` and QMP-injected `A` press/release
  reaching the firmware through nINT, GPIO 11, the ESP-IDF ISR, and producing
  raw FIFO events `0x8d` and `0x0d` without polling;
- a CPU-FIFO SPI3 transaction path that initializes the Cardputer ADV ST7789,
  renders a deterministic red/blue 240x135 framebuffer, and emits
  `SIM:DISPLAY controller=st7789 width=240 height=135 pattern=red-blue`;
- the corresponding StickS3 pins, 135x240 crop, and exact framebuffer
  assertions when the StickS3 fixture is selected;
- StickS3 octal-PSRAM initialization, an exact 8 MiB capacity assertion, and a
  deterministic 4 KiB allocation/write/read/free test;
- `reset\n` producing another boot sequence without replacing the flash image.

Board-specific keyboard/button, PSRAM, power, and sensor fixtures will extend
this base contract rather than weakening it.

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
