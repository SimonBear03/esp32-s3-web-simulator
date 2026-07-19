# Conformance strategy and evidence

## Release gate

Simulator releases must be gated by firmware owned by this repository. The
fixture will exercise boot, flash, UART, timers, reset, NVS, display transport,
board input, PSRAM where applicable, and deterministic power events. Its source
and build recipe will be pinned; generated binaries will remain untracked.

The base fixture lives at `tests/firmware/conformance/`. Board-specific
fixtures will build on its stable `SIM:` UART contract.

The 2026-07-19 two-profile fixture produced unpadded merged-image SHA-256
`2095d588cd9f83ee2d479ac3ea9e0fcb0ba33302897918e4e67cdce47d6ab74b`
for Cardputer ADV and
`5a128f26a653e77d738860bfd236710975f502715a75be15bd2f3e6ddb826e16`
for StickS3.
The service conformance runner observed TCA8418 configuration at I2C address
`0x34`, ESP-IDF `CHANGE` interrupt registration on GPIO 11, three heartbeats,
`SIM:PONG`, pause/resume, QMP reset, the UART reset command, exact four-byte NVS
write/readback equality across each boot, and runtime-directory cleanup.
The restricted test sandbox rejects Unix-domain socket creation, so the final
release-gate runs used a permitted execution boundary with each worker's normal
private QMP socket enabled. Production conformance keeps QMP mandatory.

The same 2026-07-19 release gate enabled a private GDB Unix socket for each
worker. For both Cardputer ADV and StickS3 the service paused QEMU, negotiated
the Xtensa remote protocol, read the program counter and four instruction
bytes at that address, added and removed a hardware breakpoint, single-stepped,
proved UART heartbeats remained frozen while paused, resumed under the
debugger, and observed the next heartbeat. Reset, framebuffer, inputs, NVS, IMU,
and power checks then continued in the same sessions. Espressif's target does
not advertise GDB feature XML, so the client fallback for registers 0 through
83 is pinned to QEMU's own ESP32-S3 register map and covered by a unit test.

The full Cardputer ADV and StickS3 gates were then repeated with
`--sandbox bubblewrap`. Each QEMU worker ran with new namespaces, no host
network, all capabilities dropped, nested user namespaces disabled, read-only
runtime inputs, a 16 MiB temporary filesystem, and only its session directory
writable. Both runs passed their existing boot, exact framebuffer pixels,
keyboard/button, IMU/power, NVS, UART, pause/resume, register, memory,
breakpoint, single-step, reset, and cleanup assertions. The development QEMU
binary links a temporary build-dependency tree, so that tree was supplied as an
explicit read-only conformance input; production packaging must instead list
its immutable dependency directory. `scripts/probe-worker-sandbox.py` also
confirmed no effective capabilities, no network routes, no configured forbidden
host paths, no secret-like environment keys, denied nested user namespace
creation, and a writable private scratch directory.

The pinned worker and owned Cardputer firmware were exercised through the real
service runner. QMP accepted `input-send-event` for
an `A` key down/up pair. Firmware polling the emulated TCA8418 FIFO observed
`SIM:KEY raw=0x8d` followed by `SIM:KEY raw=0x0d` with firmware polling removed.
This proves the host event, QMP, board mapping, TCA8418 nINT, GPIO 11 edge,
ESP-IDF ISR, I2C controller, device register, and firmware-read path end to end.
The service runner performs these same assertions automatically when its normal
private QMP socket is available.

The same owned firmware initializes ESP-IDF SPI3 without DMA, programs the
ST7789 visible window at controller coordinates `(40,53)` through `(279,187)`,
and writes all 32,400 visible pixels. QMP captured a P6 RGB framebuffer of
exactly 240x135. Independent host assertions found red `(255,0,0)` at `(0,0)`
and `(239,66)`, then blue `(0,0,255)` at `(0,67)` and `(239,134)`. The service
runner now performs these dimension and boundary-pixel assertions through its
private QMP socket. This proves the ESP-IDF SPI driver, ESP32-S3 general-purpose
SPI register model, ST7789 command/data model, visible crop, QEMU console, and
service parser end to end.

The StickS3 fixture separately uses its public SPI3 pin map and controller
window `(52,40)` through `(186,279)`. It passed boot, heartbeat, UART, software
reset, and NVS 1-to-2 persistence through the bounded service worker with 8 MiB
octal PSRAM enabled and the firmware's real QIO flash configuration. The
service's QMP capture reported exactly 135x240; host assertions
found red at `(0,0)` and `(134,119)`, then blue at `(0,120)` and `(134,239)`.
This run also established that QEMU pads RGB24 PPM rows to four-byte alignment
for a 135-pixel width. The service now strips that host padding and emits tightly
packed protocol RGB24, with a dedicated regression test.

The QIO conformance run exposed a four-byte read shift between the ESP32-S3
controller's physical quad-lane dummy cycles and QEMU's serialized GigaDevice
flash model. Patch 0005 supplies the model's missing preamble bytes and selects
octal PSRAM for the StickS3 profile. Exact NVS readback now passes immediately
after each write and persists across both QMP and firmware-requested resets.

Patch 0006 adds direct, active-low StickS3 button lines plus behavioral BMI270
and M5PM1 I2C devices. The QMP-enabled service gate observed A and B press and
release on firmware GPIO 11/12, BMI270 chip ID `0x24` at `0x68`, and the default
stationary sample `(0,0,4096)` at the fixture's 8 g range. A runtime event then
produced `(4096,0,0)` acceleration and `(0,0,4096)` gyro, corresponding to 1 g
X and 250 dps Z. The same run read default M5PM1 telemetry of 3900 mV battery,
5000 mV VIN, and charging, then read back an injected 3700 mV battery-only,
charging-off state. Both values persisted as environmental state across QMP
and firmware resets while NVS advanced exactly from boot 1 to 3. Cardputer ADV
then passed its full keyboard/display/NVS regression gate with the same worker.

Application repositories such as Cardputer Chess are valuable compatibility
and stress cases, but they are not release gates while they are in progress.
Their own failures must not be mislabeled as simulator failures.

## 2026-07-19 QEMU compatibility spike

The first spike used a disposable 8 MiB merged flash snapshot built from the
in-progress Cardputer Chess checkout. The snapshot is not committed. Its SHA-256
was:

```text
f819ca0b042260a7c2d2a5dab7b31e397747a0bfa3b57143d7dbb807780680e9
```

With the unmodified Espressif QEMU 9.2.2 release, ESP-IDF 4.4 aborted during
`esp_flash_init_default_chip`. SPI logging showed status-register-2 commands
being decoded incorrectly for the 8 MiB GigaDevice flash model.

With
`emulator/qemu/patches/0001-m25p80-support-gigadevice-qe-status.patch`
applied, the same snapshot completed ROM and second-stage boot, entered the
application, and stayed alive for the full 15-second observation window. The
last application-owned line was:

```text
[error] Keyboard: Unsupported board type: 137
```

QEMU then exited only because the test harness sent its timeout signal. This
proves the GigaDevice QE patch fixes the flash-initialization blocker. It did
not prove Cardputer ADV display compatibility. Keyboard and display
compatibility are now covered independently by the simulator-owned fixture and
explicit board models rather than inferred from the application snapshot.

The same snapshot was then run for four seconds through the public service's
`SessionManager`, with guest networking disabled and native worker resource
limits enabled. The manager reported `running`, captured 363 serial bytes,
stopped the process, and removed the private runtime directory. QMP socket
binding could not be exercised inside the Codex sandbox because that sandbox
rejects all Unix-domain socket binds with `EPERM`; QMP remains enabled by
default and must be live-tested in the deployment boundary.

## Evidence rules

- Record the exact QEMU commit, patch set, firmware source revision, build
  configuration, flash-image digest, run command, expected observations, and
  unexpected observations.
- Never publish a third-party application firmware image unless its licence and
  redistribution permission are explicit.
- Keep hardware-in-the-loop results separate from emulator-only results.
- A timeout is successful only when the expected heartbeat remains observable
  and no panic, reset loop, sanitizer report, or host crash occurred.

## Design references

- [M5Stack Cardputer ADV documentation](https://docs.m5stack.com/en/core/Cardputer-Adv)
  defines the ESP32-S3, display, I2C, TCA8418, and interrupt pin assignment.
- [Texas Instruments TCA8418 datasheet](https://www.ti.com/lit/ds/symlink/tca8418.pdf)
  defines the `0x34` address, 10-event FIFO, register map, and press bit.
- [M5Stack StickS3 documentation](https://docs.m5stack.com/zh_CN/core/StickS3)
  defines the StickS3 display geometry and pins.
- [Espressif QEMU supported-feature matrix](https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/README.md#supported-features)
  is the upstream baseline; this repository documents every additional patch.
- [ESP-IDF ESP32-S3 I2C API](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/peripherals/i2c.html)
  anchors the firmware-facing controller behavior.
- [ESP-IDF ESP32-S3 SPI master API](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/peripherals/spi_master.html)
  anchors the SPI3 transaction and completion behavior.
