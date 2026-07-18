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
- upstream or patched QEMU binaries;
- user firmware or ELF files;
- runtime flash, NVS, trace, log, or crash artifacts;
- M5Stack product artwork or extracted proprietary assets.

The source build is pinned and reproducible. Operators obtain upstream inputs
from their owners and must review those owners' terms before redistributing a
combined deployment artifact. `THIRD_PARTY.md` is the authoritative ledger.

## Contribution rule

Contributors must identify copied or generated material and its provenance.
Do not submit code copied from a firmware repository merely because that
firmware is used as a conformance application. Board behavior should be
implemented from public specifications, clean-room observations, and
appropriately licensed upstream code.
