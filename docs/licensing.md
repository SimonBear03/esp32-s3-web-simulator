# Licensing and redistribution

## Project licence

The public simulator is licensed under GPL-2.0-only. Source files should carry
`SPDX-License-Identifier: GPL-2.0-only` unless they are data, prose, generated
output, or governed by a documented compatible third-party licence.

This choice keeps QEMU-derived emulator work under the same licence family and
allows the complete simulator implementation to remain public. It does not
change the licences of uploaded firmware, Espressif tools or ROMs, M5Stack
libraries, or other third-party inputs.

## Process boundary

The QEMU worker is a separate executable process. The session service controls
it through command-line, QMP, GDB, character-device, and framebuffer interfaces.
Tracked QEMU patches are derivative works and therefore remain GPL-2.0-only.

The production website is separately deployed and communicates with the public
simulator service through a documented network API. Generic simulator features
must be implemented in this public repository first.

## Artifact policy

This repository does not commit or publish:

- Espressif ROM binaries;
- public upstream or patched QEMU images/binaries containing an unreviewed ROM;
- user firmware or ELF files;
- runtime flash, NVS, trace, log, or crash artifacts;
- M5Stack product artwork or extracted proprietary assets.

The source build is pinned and reproducible. Operators obtain upstream inputs
from their owners and must review those owners' terms before redistributing a
combined deployment artifact. `THIRD_PARTY.md` is the authoritative ledger.

The optional debug-symbol ELF is selected and parsed entirely in the user's
browser. It is not transferred to the public service or private site, and its
function names remain page-memory-only. This privacy boundary does not alter
the ELF or firmware owner's licence.

The rootless worker build may create an operator-local image from a separately
supplied ROM and its reviewed digest. That private runtime artifact is not a
repository distribution. Publishing or transferring it is a separate action
and remains prohibited until the ROM terms and required notices are resolved.

## Contribution rule

Contributors must identify copied or generated material and its provenance.
Do not submit code copied from a firmware repository merely because that
firmware is used as a conformance application. Board behavior should be
implemented from public specifications, clean-room observations, and
appropriately licensed upstream code.

Firmware libraries and vendor SDKs may be used as black-box conformance inputs
or to confirm public, firmware-visible behavior. Their implementation code must
not be copied into a QEMU patch unless its licence is explicitly compatible and
the provenance is recorded. The Cardputer ADV SAR ADC model is an independent
behavioral implementation based on public register/API behavior and observed
fixture results; it does not incorporate ESP-IDF or M5Unified source code.
