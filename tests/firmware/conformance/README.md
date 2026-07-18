# ESP32-S3 base conformance firmware

This simulator-owned fixture is the release gate for the base ESP32-S3 worker.
It emits a stable UART contract for boot, flash capacity, heap, NVS persistence,
timers, heartbeat continuity, byte-stream input, software reset, ESP32-S3 I2C,
and TCA8418 key-event delivery.

## Build

Install PlatformIO Core, then run from this directory:

```sh
./build-merged.sh
```

The expected merged image is
`.pio/build/qemu-esp32s3/firmware-merged.bin`. PlatformIO's generated files are
ignored and must not be committed.

The environment pins PlatformIO's Espressif32 platform to 6.12.0 (Arduino-ESP32
2.0.17). The 8 MiB image uses DIO flash at 80 MHz and UART0 rather than USB CDC.

## UART contract

Successful base conformance requires:

- `SIM:BOOT version=1 profile=esp32s3-base`;
- `SIM:FLASH bytes=8388608`;
- a monotonically increasing `SIM:NVS boot_count` after reset on the same flash;
- `SIM:READY` followed by at least three ordered `SIM:HEARTBEAT` lines;
- `ping\n` producing `SIM:PONG`;
- TCA8418 configuration at address `0x34` and QMP-injected `A` press/release
  producing raw FIFO events `0x8d` and `0x0d`;
- `reset\n` producing a new boot sequence without replacing the flash image.

Board-specific display, keyboard/button, PSRAM, power, and sensor fixtures will
extend this base contract rather than weakening it.

From the repository root, exercise the built image through the real session
service with:

```sh
make base-conformance \
  QEMU=/path/to/qemu-system-xtensa \
  ROMS=/path/to/qemu/roms \
  FIRMWARE=tests/firmware/conformance/.pio/build/qemu-esp32s3/firmware-merged.bin
```

Add `--no-qmp` directly to `scripts/run-base-conformance.py` only in a test
sandbox that denies Unix-domain sockets. Production conformance must include
QMP.
