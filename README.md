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

Repository foundation only. No simulator implementation or hosted service
exists yet.

The first conformance application is Cardputer Chess. A successful first
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

Implementation tooling and validation commands have not been selected yet.
Before importing emulator code or firmware/ROM artifacts, settle and document
the repository's component licences and third-party redistribution terms.

## Remote

No GitHub remote is configured. It will be linked after the upstream repository
is created.

## Licence

The project is intended to remain open source. The component-level licensing
plan must be finalized before implementation code is imported or published;
until then, no licence is granted beyond applicable law.
