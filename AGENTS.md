# AGENTS.md

## Project Identity

This repository owns ESP32-S3 Web Simulator: an open-source, browser-operated
firmware simulator for running real ESP32-S3 firmware against explicit virtual
device profiles. Its first profiles are M5Stack Cardputer ADV and StickS3.

It owns the web client, simulation-session service, emulator integration,
virtual board/device models, debugging surfaces, tests, and project
documentation. It does not own application firmware repositories, upstream
QEMU, Espressif ROMs and SDKs, M5Stack libraries or hardware designs, or
third-party trademarks and artwork.

## Start Here

- Read this file and `README.md`.
- Read `docs/architecture.md` before changing runtime boundaries, device
  fidelity, or emulator integration.
- Run `git status --short --branch` before meaningful edits.

## Work Mode

Before meaningful edits, classify the task:

- `Ship`: narrow documentation, tests, configuration, or low-risk fixes.
- `Branch`: emulator work, device models, web product work, runtime isolation,
  dependency changes, or other multi-file/experimental work.
- `Ask`: semantic readiness is unclear, the dirty diff is mixed, or a licensing
  boundary needs Simon's judgment.
- `Stop`: secrets, destructive Git, history rewrite, force push, unsafe
  execution of user firmware, or unlicensed third-party imports.

## Branching And Git

- Keep `main` buildable and easy to pull.
- Simon has authorized direct work on `main` for the initial simulator build.
  Keep each commit coherent and validated so `main` remains usable throughout
  the build.
- Use a short-lived branch only when Simon requests one or a later experiment
  should not land incrementally on `main`.
- Inspect dirty changes before pulling, committing, or pushing.
- Commit only coherent, reviewed, validated work.
- Do not reset, stash, clean, force-push, or discard work unless Simon
  explicitly asks.

## Validation

Run the foundation checks with:

```sh
make check
```

Document and run component-specific tests as soon as code is introduced.
Firmware conformance must use real merged images or ELF files, not a substitute
application runtime.

## Licensing And Third-Party Material

- Keep the project open source, but do not select or change its primary licence
  casually.
- Do not copy or bundle QEMU code, Espressif ROM binaries, M5Stack artwork,
  firmware images, or other third-party material until its licence and
  redistribution terms are recorded.
- Keep QEMU-derived work and web-service/client boundaries explicit, with SPDX
  identifiers and third-party notices where applicable.
- Prefer original device artwork and compatibility wording; do not imply
  endorsement by Espressif or M5Stack.
- Never commit user-uploaded firmware. It is untrusted, ephemeral runtime input.

## Secrets And Runtime

Never commit credentials, `.env` files, private keys, uploaded firmware,
emulator state, saved NVS images, crash dumps, logs, or session data. Runtime
workers must treat firmware as untrusted code and enforce isolation, resource
limits, timeouts, and cleanup.

## Workspace Memory Bridge

When a containing Simon workspace provides `system/pkm_memory_bridge.md` and
`9_pkm/`:

- Follow the bridge after meaningful project work.
- Read `9_pkm/AGENTS.md` before writing to the vault.
- Keep project and PKM changes separate; report pending memory handoffs.

When opened independently, follow this repository guide only.

## Reporting

If work is dirty, incomplete, blocked, unvalidated, hardware-unverified, or
intentionally unpushed, report the affected files, reason, and next safe step.
