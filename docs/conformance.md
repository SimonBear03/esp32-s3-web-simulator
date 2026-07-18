# Conformance strategy and evidence

## Release gate

Simulator releases must be gated by firmware owned by this repository. The
fixture will exercise boot, flash, UART, timers, reset, NVS, display transport,
board input, PSRAM where applicable, and deterministic power events. Its source
and build recipe will be pinned; generated binaries will remain untracked.

The base fixture lives at `tests/firmware/conformance/`. Board-specific
fixtures will build on its stable `SIM:` UART contract.

The 2026-07-19 keyboard-capable base build produced unpadded merged-image
SHA-256
`6d3f125e32121aee76a601f12062381f8b32de0e11b41fa8e7c47c8465757dfb`.
The service conformance runner observed TCA8418 configuration at I2C address
`0x34`, ESP-IDF `CHANGE` interrupt registration on GPIO 11, three heartbeats,
`SIM:PONG`, a software reset, a second boot, NVS incrementing from 1 to 2,
continued heartbeats, and runtime-directory cleanup.
The Codex sandbox required the runner's Unix-socket QMP path to be disabled;
production conformance keeps QMP mandatory.

The same pinned worker and owned firmware were therefore exercised with QMP on
stdio and UART in a separate private file. QMP accepted `input-send-event` for
an `A` key down/up pair. Firmware polling the emulated TCA8418 FIFO observed
`SIM:KEY raw=0x8d` followed by `SIM:KEY raw=0x0d` with firmware polling removed.
This proves the host event, QMP, board mapping, TCA8418 nINT, GPIO 11 edge,
ESP-IDF ISR, I2C controller, device register, and firmware-read path end to end.
The service runner performs these same assertions automatically when its normal
private QMP socket is available.

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
proves the GigaDevice QE patch fixes the flash-initialization blocker. It does
not prove Cardputer ADV display compatibility. Keyboard compatibility is now
covered independently by the simulator-owned fixture and explicit I2C/TCA8418
models rather than inferred from the application snapshot.

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
- [Espressif QEMU supported-feature matrix](https://github.com/espressif/esp-toolchain-docs/blob/main/qemu/README.md#supported-features)
  is the upstream baseline; this repository documents every additional patch.
- [ESP-IDF ESP32-S3 I2C API](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32s3/api-reference/peripherals/i2c.html)
  anchors the firmware-facing controller behavior.
