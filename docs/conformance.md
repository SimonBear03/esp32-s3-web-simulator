# Conformance strategy and evidence

## Release gate

Simulator releases must be gated by firmware owned by this repository. The
fixture will exercise boot, flash, UART, timers, reset, NVS, display transport,
board input, PSRAM where applicable, and deterministic power events. Its source
and build recipe will be pinned; generated binaries will remain untracked.

The base fixture lives at `tests/firmware/conformance/`. Board-specific
fixtures will build on its stable `SIM:` UART contract.

The 2026-07-19 two-profile fixture produced unpadded merged-image SHA-256
`fca5adb5dc4fc66097379e7d5c0ecad7331f93b3373a39cdbc6e4d4b826b160f`
for Cardputer ADV and
`25d201b87156991becc7fb168b642dd63fb56d5cbe803e5c337a0083a4024b04`
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
service runner. QMP accepted repeated `input-send-event` requests for `W`, `A`,
`S`, `D`, and Enter down/up pairs. Firmware reading the emulated TCA8418 FIFO
observed exact pairs `0x8c/0x0c`, `0x8d/0x0d`, `0x91/0x11`, `0x97/0x17`, and
`0xc3/0x43` with firmware polling removed. This proves the host event, repeated
QMP connection, board mapping, TCA8418 nINT, GPIO 11 edge, ESP-IDF ISR, I2C
controller, device register, and firmware-read path end to end. The service
runner performs these same assertions automatically when its normal private
QMP socket is available.

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

Patch 0009 attaches a separate behavioral BMI270 to the Cardputer ADV internal
I2C bus and adds the ESP32-S3 RTC-controller ADC1 path used by the board's
GPIO10 battery divider. The owned firmware identified BMI270 chip ID `0x24`,
read the default stationary sample `(0,0,4096)`, and read an injected 1 g X /
250 dps Z sample as `(4096,0,0)` and `(0,0,4096)`. Its normal ADC API reported
the default model as 3898 mV battery / raw 2107, then a 3700 mV injected battery
as 3704 mV / raw 2001. Firmware reports charging as unavailable, matching the
physical Cardputer ADV API instead of inventing VIN or charge-status telemetry.
The model uses an independently implemented behavioral transfer approximation
and nominal calibration eFuse state; no ESP-IDF or M5Stack source is copied into
the GPL patch.

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

## 2026-07-19 Cardputer Chess web compatibility proof

The next compatibility run used the unmodified Cardputer Chess checkout at
commit `5699ef4e5d0f0dc20d8b2775511a66ab4e81db04`. Its locally generated merged
image was 617712 bytes with SHA-256:

```text
2584687edc66495863c591ec7893331b15cc97aaf302c28c560a43c9ade93b4e
```

The image is not committed. Host tests passed 213 assertions in both the normal
and sanitizer runs, and its PlatformIO `cardputer-adv` build used 52.4% of RAM
and 16.5% of flash. These application checks establish a useful input baseline;
they do not make the in-progress Chess repository a simulator release gate.

Espressif QEMU commit `40edccac415693c5130f91c01d84176ae6008566`
with tracked patches 0001 through 0008 ran the image for 25 seconds inside the
Bubblewrap worker boundary. The session remained `running`, returned no worker
exit code, and emitted no panic, reset loop, stack-canary failure, or browser
error.

The actual React workbench then uploaded the same merged image and waited 12
seconds before requiring three identical framebuffer samples. The stable
240x135 frame rendered the recognizable `CARDPUTER CHESS` setup screen rather
than accepting boot-time pixel activity. Pressing the simulated `S` key through
the web keyboard and TCA8418 path moved the selection from `Play as` to `Level`;
the resulting frame again stabilized for three samples. The two deterministic
RGB hashes differed (`4192754852` then `3632196620`).

This proves boot, current M5GFX board detection, SPI3/ST7789 rendering, browser
framebuffer delivery, and one real keyboard transition for the application.
It does not yet prove application NVS behavior or completion of a full game.

## 2026-07-19 newest Cardputer Chess behavioral proof

After the in-progress Chess UI advanced, the compatibility target moved to the
unmodified remote revision
`99503e035ed0eece99fd544f4ccaffe7081e10e9`. Its locally generated 618848-byte
merged image had SHA-256:

```text
732a79a2990635384ee6a9d43cbde9a120b990b8f7e692acdf4036c908e4454a
```

The firmware build used 53.7% of configured RAM and 16.5% of configured flash.
The image is test input only and is not committed or redistributed by this
repository.

The exact image booted unmodified inside the Bubblewrap worker and rendered its
new setup UI. Changing the saved level produced framebuffer SHA-256
`00204fa4bb8c30727a96df3c595ddfd1c937758d296d19f6abfb38e0375fcc13`
both before and after a QMP reset, proving application-level Preferences/NVS
persistence rather than only fixture-level storage. Starting a game produced
framebuffer SHA-256
`2f13da479580702cacd832dd9557e337bdc19f428c3588f5c74247d3e8b72ddf`.
Real Cardputer key events then played `e2-e4`; the firmware's embedded ESP32
search replied `c7-c6`, and the settled framebuffer SHA-256 was
`9494f08035ad87582d4304f8b0104a8aa9b3829ce4fbd63a060d2c81ed47da8f`.
The worker remained running with no panic, stack-canary failure, or reset loop.

This run exposed a simulator-owned QMP cleanup defect: after QEMU had accepted
an input event and returned its matching response, its immediate peer close
could be re-raised by `asyncio` during `wait_closed()` and falsely report the
successful key request as failed. Public-core commit `b6e0754` closes the
one-shot transport after the response without waiting for peer shutdown. Unit
coverage and the exact application rerun both passed after that change.

The preceding Chess revision at `5699ef4` also exposed application-owned stack
overflows when entering a game and then starting its search task. Those were
separated with a disposable stack-only diagnostic build and were never treated
as emulator failures.

A follow-up run drove the newest unmodified revision through real Cardputer key
events for a complete 39-ply legal game. A host UCI process chose only the human
side's legal moves; every black move was computed inside the emulated ESP32 and
discovered from the firmware's rendered last-move squares. The game was:

```text
1. Nc3 e5 2. Nf3 b5 3. Nxe5 Qf6 4. d4 a5 5. Nxb5 Be7
6. Nxc7+ Kd8 7. Nxa8 Nh6 8. Bd2 Na6 9. Bxa5+ Qb6
10. Bxb6+ Nc7 11. Bxc7+ Ke8 12. Nb6 f6 13. Nxc8 Nf7
14. Nxe7 h5 15. N5g6 Nh6 16. Nxh8 Nf7 17. Nhg6 Nh8
18. e4 Nf7 19. Nf5 d6 20. Bb5# 1-0
```

The game-over framebuffer SHA-256 was
`6e0d8fa2adb1aa2ec73c95fdafef585820f74bbee9cd9ae11a55c507f86c1a3c`.
The worker remained `running`, displayed `White wins`, accepted Enter through
the keyboard, and returned to setup with framebuffer SHA-256
`e8bb7351716a3e987de41b23bb95eb130fd0a8879122abe8ce2740439abe4028`.
This completes the application-level boot, NVS, display, keyboard, embedded
search, checkmate, game-over, and new-game compatibility milestone without
modifying or redistributing the application firmware.

After patch 0009 added Cardputer ADV IMU and ADC behavior, the same unmodified
image was rerun as a regression gate inside Bubblewrap. Its saved-level frame
again matched exactly before and after QMP reset. A fresh legal game completed
in 29 plies (`1. e4 c5 2. Nf3 Nc6 3. d4 cxd4 4. Nxd4 Nf6 5. Nc3 Ng8 6. Be3
Na5 7. Ndb5 b6 8. Nd5 f6 9. Ndc7+ Kf7 10. Qd5+ e6 11. Nxe6 Bb4+ 12. c3 Bf8
13. Nxd8+ Ke7 14. Qf7+ Kxd8 15. Qxf8#`). The worker remained running at
checkmate, produced game-over framebuffer SHA-256
`673a007bebfec152a568a5957fdd4625626ce701dc7776215649a51684cc210a`,
and returned to the same setup frame after Enter. This confirms the added
devices and nominal eFuse calibration do not regress the complete Chess path.

## 2026-07-19 native trace and replay release gate

Espressif QEMU commit `40edccac415693c5130f91c01d84176ae6008566`
with tracked patches 0001 through 0011 produced QEMU 9.2.2 binary SHA-256
`88003d34f2e614754fc02bf49f8c44aed755cb9d85ce31f356fe919b4c0c0719`.
The build had SLiRP disabled, no non-system runtime search path, and no missing
dynamic library. Patch 0010 supplied native board-device tracepoints; patch
0011 made the no-SLiRP feature gate effective.

The owned Cardputer ADV fixture SHA-256
`fca5adb5dc4fc66097379e7d5c0ecad7331f93b3373a39cdbc6e4d4b826b160f`
passed inside Bubblewrap with QMP and GDB enabled. In addition to the existing
boot, framebuffer, input, IMU, ADC, UART, NVS, debugger, and cleanup contract,
the run observed native ADC, display command/window, GPIO, I2C, SPI, keyboard,
and IMU trace types. Repetitive sources produced explicit sampling markers
without crowding out the later interactive traces. Fifteen accepted external
actions then replayed from the normalized original flash image into generation
2 at their recorded offsets. Replay reached the same injected motion and power
values and the same final NVS boot count of 3 before reporting `completed`.

The owned StickS3 fixture SHA-256
`25d201b87156991becc7fb168b642dd63fb56d5cbe803e5c337a0083a4024b04`
passed the equivalent boundary. It observed native display, GPIO, I2C, SPI,
button, IMU, and M5PM1 power traces, then replayed all nine external actions
into generation 2 and reached the same NVS boot count of 3. These two runs are
the release gate for bounded recording, per-source trace sampling, baseline
restoration, timed external-input replay, and worker generation rollover.

## 2026-07-19 historical Cardputer Chess branch separation

At that point, the Cardputer Chess `main` revision
`5699ef4e5d0f0dc20d8b2775511a66ab4e81db04` built successfully, and its
617712-byte merged image SHA-256 remained
`2584687edc66495863c591ec7893331b15cc97aaf302c28c560a43c9ade93b4e`.
It booted, rendered, accepted setup input, and preserved its selected level
exactly across QMP reset, but entering a game reproduced its application-owned
`loopTask` stack overflow. This image is therefore not a simulator release
failure and is not described as the newest healthy application target.

The then-newest remote repair branch `fix/cardputer-start-flicker` at unmodified
revision `85b2672de49581aa26951e31e930584b2b3a292b` built with 53.7% of
configured RAM and 16.5% of configured flash. Its 618848-byte merged image had
SHA-256
`3d36f9221ca7958ca9d6ea3aeebf990199a003ce586ab35a2a5e02bad67a23fa`.
Inside the same traced Bubblewrap worker, its saved-level framebuffer SHA-256
`4c997b51aed7a1cf0ef1dfe176b6a0d25b00fcf7ab6074cdd79c77744ce7c833`
matched before and after QMP reset. Real Cardputer key events then completed a
15-ply legal game (`1. e4 c5 2. Nf3 Nc6 3. Bb5 f6 4. d4 g5 5. Nxg5 Ne5
6. dxe5 h5 7. exf6 a5 8. f7#`). The game-over framebuffer SHA-256 was
`4aa3c9b7c3b726174c16e84cba29158ee2a734def7eb6dc0d6f50a965be7171b`;
the worker remained running and Enter returned to setup. No Chess firmware or
build output is distributed by this repository.

## 2026-07-20 current Cardputer Chess main and startup proof

The current clean Cardputer Chess `main` revision
`20da6c957c15c0e1ec79220f1d32a2885ac9a3b8` passed all 286 normal host tests
and all 286 ASan/UBSan tests. Its PlatformIO `cardputer-adv` build used 178188
of 327680 bytes of RAM (54.4%) and 555641 of 3342336 bytes of flash (16.6%).

The application partition table places `app0` at `0x10000`. An initial
disposable diagnostic image mistakenly placed `firmware.bin` at `0x20000`;
QEMU correctly showed a black framebuffer and a tight `RTC_SW_SYS_RST` boot
loop because the selected application slot was erased. Rebuilding the private
test image with bootloader at `0x0`, partitions at `0x8000`, `boot_app0` at
`0xe000`, and the application at `0x10000` produced a 621536-byte merged image
with SHA-256:

```text
1a0334abc6db19b07637ad02aa6c70fb21969e2b183ab35a0189a893ce20a7a3
```

Byte comparisons verified the partition table, boot selector, and application
at those offsets. The service normalized it to an 8 MiB private flash image
with SHA-256
`9bbae8293741f266de927dd4cc50daad510b73c24c16179604a3d5e79a18c287`.
Neither image is committed or redistributed.

The exact image then ran unmodified through the real service API inside a
Bubblewrap worker with QMP, private GDB, native peripheral tracing, resource
limits, and a hardened temporary systemd unit. The service did not expose the
session until QMP returned `running`. The 240x135 setup framebuffer had SHA-256
`75ea832b2870f737e912db49f542cb7ecff3b17b61cddfd18b89ae23b3c86233`.
Real `S` press/release input moved the selection to Level and produced
`624fdfcf7ddaf71c3cfbdbd28eeba28314a213706f6b0fe4c51c9e723daa7189`.
Real `D` press/release changed the choice to `5 Strong` and produced
`179cb28b610a6998b4f4f06880bc9e34dc1fb2d17613ca1b9b156f03c9083a63`.
After QMP reset, visual inspection confirmed `5 Strong` remained selected in
Preferences/NVS; the reset setup frame, whose highlight returned to the first
row, was
`4c744c212ee2c610c82787aeb04c476f1bc0fe2cc86fb3971d87084789c3ff59`.
Enter then opened the game screen with framebuffer SHA-256
`c6b8e3c30ada7b660e3bc475059b587662ad4c1d49b8a3cad0637870aa2fa8e4`.
The worker remained `running` and the API deletion completed cleanly.

The paginated bounded timeline contained 676 events. Native TCA8418 tracing
recorded all six transitions: `S` as event code 17 down/up, `D` as code 23
down/up, and Enter as code 67 down/up, each entering an empty FIFO before
firmware consumption. UART showed one normal power-on boot and no panic or
reset loop.

This run also closed three simulator-owned startup defects. The manager now
rejects runtime roots that cannot fit private Unix sockets, waits through only
QEMU's bounded `prelaunch` transition before publishing a session, and fails
closed while terminating an unready worker. Native trace output now uses the
QEMU log backend's inherited stderr instead of reopening `/dev/stderr`, which
fails when Uvicorn/uvloop supplies a socketpair. The high-volume trace reader
also yields cooperatively so QMP control work cannot be starved.

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
