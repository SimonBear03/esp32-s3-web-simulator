# ESP32-S3 Web Simulator

ESP32-S3 Web Simulator is an open-source project for running real ESP32-S3
firmware in a browser-operated virtual device before flashing physical
hardware.

The first device profiles will target:

- M5Stack Cardputer ADV
- M5Stack StickS3

The intended workflow is to upload or build a merged firmware image, flash it
into an isolated simulation session, interact with the virtual display and
controls, inspect serial/debug state, and then flash the validated image to a
physical device.

## Status

Active implementation. The server-side worker boots real merged ESP32-S3 flash
images, preserves private flash/NVS state for a session, streams bidirectional
UART, and supports reset and bounded worker lifecycles. The Cardputer ADV model
now includes the ESP32-S3 I2C path and a TCA8418 keyboard FIFO with typed web
input translated through QMP. Cardputer ADV and StickS3 now have SPI3/ST7789
display models with correctly sized RGB framebuffers; the Cardputer path is
covered by real compiled firmware and exact pixel assertions. Power, sensor,
debugger, continuous web-frame streaming, and hosted-web milestones remain in
progress.

Cardputer Chess is a compatibility and stress application, not the owned
release gate while that application is itself in progress. A successful first
device milestone means its unmodified firmware can boot, render through the
virtual ST7789 display, receive TCA8418 keyboard input, use persistent NVS, and
complete a game through the web interface.

## Product Boundary

The simulator aims to model deterministic development surfaces:

- ESP32-S3 CPU, boot, flash, memory, timers, reset, and watchdog behavior
- device display and controls
- serial output and debugging
- NVS persistence
- logical battery, USB, sleep, wake, and brownout states
- scripted or interactive virtual sensor input

It will not initially claim physical validation of BLE/RF behavior, electrical
current draw, thermals, acoustic output, or real IMU noise and calibration.

See [docs/architecture.md](docs/architecture.md) for the initial system and
licensing boundaries.

## Development

The emulator baseline is Espressif QEMU 9.2.2 built from a pinned source commit
with tracked flash, I2C, GPIO, keyboard, SPI, and display patches. See
[emulator/qemu/README.md](emulator/qemu/README.md) for native prerequisites and
the reproducible build command.

Licensing and redistribution decisions are recorded in
[docs/licensing.md](docs/licensing.md) and [THIRD_PARTY.md](THIRD_PARTY.md).
Firmware, ROMs, emulator binaries, and runtime session state are never committed.
The release-gate policy and current boot-spike evidence live in
[docs/conformance.md](docs/conformance.md).

Run the repository foundation checks with:

```sh
make check
```

`make check` validates repository policy, lints the service, and runs its test
suite. The versioned browser/service contract is documented in
[docs/protocol.md](docs/protocol.md).

## Remote

`origin` points to the public GitHub repository:

`git@github.com:SimonBear03/esp32-s3-web-simulator.git`

## Licence

The project is open source under GPL-2.0-only. Third-party components and
runtime artifacts retain their own terms as documented above.
