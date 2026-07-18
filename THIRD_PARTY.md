# Third-party components

This ledger records the source, version, licence, distribution mode, and role
of every third-party component that is material to the simulator. It must be
updated before a new component or artifact is committed or distributed.

| Component | Pinned version | Licence | Distribution in this repo | Role |
| --- | --- | --- | --- | --- |
| Espressif QEMU | `esp-develop-9.2.2-20260417` (`40edccac415693c5130f91c01d84176ae6008566`) | GPL-2.0-only overall; individual files may carry compatible notices | Source is not vendored. A reproducible build script fetches the pinned upstream commit and applies the tracked GPL patch. No binary is committed. | ESP32-S3 CPU and SoC emulation |
| Espressif ESP32-S3 ROM image | From the pinned Espressif QEMU release | Separate Espressif terms; redistribution review pending | Not committed or redistributed. A local operator supplies an artifact obtained from Espressif. | First-stage boot ROM required by the QEMU machine |
| PlatformIO Espressif32 / Arduino-ESP32 | Platform `6.12.0`; Arduino-ESP32 `2.0.17` | Apache-2.0 and component-specific notices | Build dependency only; generated packages and firmware are not committed | Builds the simulator-owned conformance firmware |
| Texas Instruments TCA8418 documentation | TCA8418 datasheet, current design reference | TI documentation terms | Documentation is not copied or redistributed | Authoritative register and FIFO behavior for the original QEMU device model |
| M5Stack M5Cardputer library | Reference commit `2d4fa6646e4e5b47e0af96214b003aa7b15b8d81` | MIT | Not vendored; no source code copied | Cross-checks public Cardputer keyboard layout and event remapping |
| M5Stack device names | Cardputer ADV and StickS3 compatibility references | Third-party trademarks | Text compatibility references only; no official product artwork | Identifies target hardware profiles |

## Boundary rules

- Uploaded firmware, ROM images, QEMU binaries, flash images, NVS state, and
  session diagnostics are runtime artifacts and must never be committed.
- QEMU-derived patches remain GPL-2.0-only and live under
  `emulator/qemu/patches/`.
- Original simulator service and client code is distributed under the
  repository licence.
- The private production-site repository consumes the public simulator through
  its documented API. It does not copy QEMU-derived source.
- Before distributing a production image containing an Espressif ROM, replace
  the pending ROM entry above with a reviewed redistribution conclusion and
  the applicable notice.
