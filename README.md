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
display models with correctly sized RGB framebuffers and live binary WebSocket
streaming. Both profiles are covered by real compiled firmware, exact pixel
assertions, NVS reset persistence, and pause/resume/reset controls; StickS3 also
passes its real QIO-flash plus 8 MiB octal-PSRAM configuration. Power, sensor,
and button input are live on StickS3 through behavioral BMI270 and M5PM1
models. Cardputer ADV now accepts deterministic BMI270 motion and battery
voltage through the same typed web protocol; firmware observes its battery
through the real GPIO10 ADC1 divider path. The unmodified Cardputer Chess
firmware now boots, preserves preferences across reset, renders and accepts
TCA8418 keyboard input through the web workbench, and has completed a 39-ply
game through checkmate and back to setup. It remains an application
compatibility milestone rather than the owned release gate. The responsive
React workbench now supports local
firmware checks, real session lifecycle controls, live framebuffer and UART
streams, virtual device inputs, deterministic sensor/power controls, and the
bounded debugger on desktop and portrait layouts. It also exposes a bounded
typed timeline, privacy-preserving diagnostics download, native peripheral
traces, and deterministic external-input replay from the originally uploaded
flash/NVS baseline. The debugger
supports synchronized pause/resume, Xtensa register snapshots, memory reads,
hardware breakpoints, and single-step on both profiles. QEMU's raw GDB socket
remains private to each worker and is never proxied to a browser. The firmware
rail also accepts an optional matching Xtensa ELF for function symbolication.
The browser validates and indexes that ELF locally, keeps it out of every HTTP
request and saved-app slot, and can decode pasted panic/backtrace addresses
plus the paused program counter. For ESP-IDF images it compares the ELF SHA-256
against the application descriptor and blocks a mismatched symbol build.
Resolved function addresses also appear automatically beneath the bounded live
UART transcript when matching symbols are active.
Production workers can run inside the tested
Bubblewrap boundary. The selected hostile
internet boundary is now implemented as a peer-credential-gated broker in
front of a dedicated rootless OCI daemon: the API never receives Docker
authority, and each digest-pinned worker gets no network, a read-only root,
no capabilities, seccomp/AppArmor, cgroup limits, QEMU's inner sandbox, and
one validated session bind. Anonymous execution remains disabled until the
live host acceptance suite proves every layer is active. Both board
conformance suites already pass through the Bubblewrap rollback boundary.
The same open-source workbench now detects an optional same-origin hosted
access contract. A deployment can offer explicit sign-in through a configured
Supabase publishable key, anonymous access through a server-validated Turnstile
challenge, or both. The browser exchanges a Supabase access token once for an
opaque same-origin HttpOnly gateway cookie; the public core never receives that
token or owns an account database. Anonymous mode maintains only the short-lived
session heartbeat. Standalone/local use is unchanged when the contract is
absent. A signed-in hosted gateway may also advertise an encrypted ten-slot app
library. The workbench keeps “Save selected” separate from “Start session,”
hides storage entirely from anonymous users, and runs each saved app in a fresh
temporary core session.

Cardputer Chess is a compatibility and stress application, not the owned
release gate while that application is itself in progress. Its unmodified
firmware has passed boot, virtual ST7789 rendering, TCA8418 input, persistent
application NVS, embedded move search, checkmate, and return-to-setup proofs.
The current tested `main` revision and its exact evidence are recorded in
`docs/conformance.md`; historical application failures remain separated from
simulator release failures there.

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
licensing boundaries. The current trust boundary and production hardening gates
are explicit in [docs/security.md](docs/security.md).

## Development

The emulator baseline is Espressif QEMU 9.2.2 built from a pinned source commit
with tracked flash, I2C, GPIO, keyboard/button, SPI, display, PSRAM, IMU, and
power/ADC patches. See
[emulator/qemu/README.md](emulator/qemu/README.md) for native prerequisites and
the reproducible build command. The production image and broker boundary are
documented in [docs/worker-isolation.md](docs/worker-isolation.md).

Licensing and redistribution decisions are recorded in
[docs/licensing.md](docs/licensing.md) and [THIRD_PARTY.md](THIRD_PARTY.md).
Firmware, ROMs, emulator binaries, and runtime session state are never committed.
The release-gate policy and current boot-spike evidence live in
[docs/conformance.md](docs/conformance.md).

Run the repository foundation checks with:

```sh
cd web && npm ci && cd ..
make check
```

`make check` validates repository policy, lints and tests the service, and
type-checks, tests, and produces a release build of the browser client. Install
the Playwright Chromium runtime once and run rendered browser checks with:

```sh
cd web
npx playwright install chromium
npm run test:e2e
```

For local development, run the service on port 8000 and the Vite client on port
4173 in separate shells. Vite proxies the versioned HTTP and WebSocket API:

```sh
UV_CACHE_DIR=/tmp/esp32-s3-uv-cache uv run uvicorn esp32_s3_simulator.api:app --app-dir src --reload
cd web && npm run dev
```

The QEMU worker still requires the pinned emulator binary and ROM configuration
described in [emulator/qemu/README.md](emulator/qemu/README.md). The versioned
browser/service contract is documented in
[docs/protocol.md](docs/protocol.md).

Controlled deployments can set `SIMULATOR_WORKER_SANDBOX_MODE=bubblewrap` and
run the denial probe:

```sh
UV_CACHE_DIR=/tmp/esp32-s3-uv-cache make sandbox-probe
```

Direct worker mode remains the local-development default. Anonymous public
execution must use `SIMULATOR_WORKER_SANDBOX_MODE=oci-broker`, the dedicated
rootless worker identity, and every live acceptance gate in
[docs/worker-isolation.md](docs/worker-isolation.md). It must also use the
ownership gateway and hardened service configuration in
[docs/security.md](docs/security.md); failed isolation never falls back to a
weaker mode.

The web client treats `/anonymous/config` as the optional hosted-access contract;
a `404` means standalone mode. Despite the legacy route name, the response can
advertise account auth, anonymous auth, or both. In Supabase mode the response
contains only the project URL and publishable key. The dynamically loaded
official client persists its browser-origin session, does not inspect URL
fragments for tokens, and exchanges the current access token through
`/auth/exchange`; the gateway returns only an HttpOnly cookie. Anonymous mode
can instead require a challenge and `/v1/sessions/{id}/heartbeat`. The browser
never receives the Turnstile secret or stores either gateway capability in
JavaScript.

When the optional hosted response identifies a signed-in account and advertises
saved apps, the workbench uses owner-scoped `/v1/saved-apps` routes for explicit
create, replace, rename, list, run, and delete actions. The public core does not
store accounts or saved firmware; storage encryption, quotas, backup, and
ownership remain private-gateway responsibilities.

## Remote

`origin` points to the public GitHub repository:

`git@github.com:SimonBear03/esp32-s3-web-simulator.git`

## Licence

The project is open source under GPL-2.0-only. Third-party components and
runtime artifacts retain their own terms as documented above.
