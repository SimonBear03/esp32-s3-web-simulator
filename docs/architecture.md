# Initial Architecture

## Product Contract

The simulator accepts the same merged ESP32-S3 firmware image or ELF intended
for physical hardware and executes it without replacing the firmware's runtime
or application APIs.

The web interface should provide a virtual device shell, framebuffer, controls,
serial console, debugger, power controls, and deterministic event recording.

## Runtime Boundary

The initial deployment direction is server-side emulation:

```text
Browser client
  device UI, input, serial, bounded hosted-access UI
  optional Supabase browser session using publishable project configuration
             |
        documented WebSocket/API protocol
             |
Private hosted gateway (production)
  account or hashed anonymous capability, origin policy, atomic quotas
             |
Simulation session service
  validation, quotas, recording; no Docker authority
             |
Peer-credential-gated worker broker
  fixed policy only; owns dedicated rootless Docker endpoint
             |
One emulator worker per active session
  digest-pinned OCI + QEMU; ESP32-S3 and board device models
```

The browser protocol should remain engine-neutral so a future open-source
client-side WebAssembly engine can implement the same contract.

The hosted-access extension is optional and same-origin. A missing
`/anonymous/config` route means standalone mode. The response may advertise a
Supabase account flow, anonymous access, or both. In account mode the browser
uses only the configured project URL and publishable key, then exchanges a
short-lived access token for an opaque gateway cookie. Production token
verification and user-to-owner mapping belong to the private gateway; neither
the token nor Supabase dependency enters the simulator core.

In anonymous mode, Turnstile verification is delegated over a protected Unix
socket to a minimal process that has the Turnstile secret and fixed Cloudflare
egress but no database, Docker, core, worker, or firmware authority. The account
verifier follows the same separate-UID pattern with only a publishable key and a
fixed Supabase user-validation request. This avoids granting internet egress or
either verifier responsibility to the gateway process.

The same optional response can advertise account-only saved apps. The public
workbench then shows a ten-slot library only when `access_kind=account` and
`saved_apps_enabled=true`. Saving is a separate explicit action from starting a
session; a selected image is never persisted just because it is run. The
browser sends raw firmware only to the owner-scoped hosted storage route and
never receives storage keys, object IDs, ciphertext, or another account's
metadata. Running a slot asks the gateway to create a normal fresh core
session, so the public core remains account- and retention-unaware. Anonymous
capabilities never see the library.

## Initial Device Models

### Cardputer ADV

- ESP32-S3FN8 with 8 MB flash and no PSRAM
- ST7789-compatible 240 x 135 display path
- TCA8418 keyboard controller and key events
- deterministic virtual BMI270 input
- GPIO10 ADC1 battery-divider voltage input
- NVS-backed preferences and simulated reset/power cycles
- serial output, FreeRTOS behavior, and debugger integration

### StickS3

- ESP32-S3-PICO-1-N8R8 with 8 MB flash and 8 MB PSRAM
- ST7789-compatible 135 x 240 display path
- active-low physical button inputs on GPIO 11/12
- M5PM1 logical power/battery states and NVS
- deterministic virtual BMI270 input

## Application Compatibility Milestones

Cardputer Chess is the first compatibility and stress application. The
simulator should boot its unmodified merged firmware, display the real UI,
accept keyboard controls, preserve preferences across restarts, and support
playing a complete game. Because that application is in progress, it does not
replace the simulator-owned conformance firmware as the release gate.

Unmodified application revisions have completed that milestone. The current
tested `main` revision `20da6c9` renders its setup and game screens, accepts
real TCA8418 input, and preserves its selected level across simulated reset.
Earlier revisions also played through checkmate and returned to setup. Exact
current and historical evidence remains in `docs/conformance.md`; owned
firmware continues to gate releases.

The existing StickS3 companion is the second acceptance application for display,
buttons, NVS, overlays, and graceful behavior when BLE is unavailable.

## Debugging Contract

The product currently exposes:

- bidirectional UART and pause, resume, and reset;
- breakpoints plus CPU register and memory inspection;
- single-step and synchronized debugger stop state through private GDB
  integration;
- bounded typed event recording and privacy-preserving diagnostics;
- native SPI, I2C, GPIO, display, input, IMU, power, and ADC traces;
- deterministic external-input replay from the uploaded flash/NVS baseline.

The browser-facing debugger is deliberately narrower than GDB. It permits
register reads, memory reads of at most 4096 bytes, at most 32 hardware
breakpoints, and single-step only while paused. It does not permit memory or
register writes and never exposes raw GDB or QMP.

Later debugging work should add:

- panic/backtrace decoding and source symbols from an explicitly uploaded ELF;
- instruction/timing traces and back-in-time CPU-state replay.

## Power Fidelity

The initial model is behavioral, not an electrical circuit simulator. Cardputer
ADV exposes battery voltage through its GPIO10 ADC1 divider; its hardware API
does not provide charging status or charge current. StickS3 exposes logical
battery, VIN, and charging values through M5PM1. Later work should represent
sleep/deep sleep, wake sources, reset, and injected brownouts. Accurate current
consumption, ADC noise, per-device calibration, and thermal estimates require
physical-device measurements.

## Licensing Boundary

QEMU and QEMU-derived device models must retain their required copyleft terms.
The web client and orchestration service should communicate with emulator
workers over a documented process/network protocol rather than assume that all
components can be relicensed as one work.

Do not bundle Espressif ROM binaries until their redistribution terms have been
verified. Do not copy official M5Stack product artwork; create original device
visuals and identify profiles as compatible devices without implying
endorsement.

The private deployment may build an operator-only image from an independently
reviewed ROM file and expected digest. The public repository and default build
context do not contain that ROM, and the resulting image must not be published
until redistribution review is complete.
