# Conformance strategy and evidence

## Release gate

Simulator releases must be gated by firmware owned by this repository. The
fixture will exercise boot, flash, UART, timers, reset, NVS, display transport,
board input, PSRAM where applicable, and deterministic power events. Its source
and build recipe will be pinned; generated binaries will remain untracked.

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
not prove Cardputer ADV keyboard or display compatibility; those require the
simulator-owned fixture and explicit peripheral models.

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
