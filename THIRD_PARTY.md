# Third-party components

This ledger records the source, version, licence, distribution mode, and role
of every third-party component that is material to the simulator. It must be
updated before a new component or artifact is committed or distributed.

| Component | Pinned version | Licence | Distribution in this repo | Role |
| --- | --- | --- | --- | --- |
| Espressif QEMU | `esp-develop-9.2.2-20260417` (`40edccac415693c5130f91c01d84176ae6008566`) | GPL-2.0-only overall; individual files may carry compatible notices | Source is not vendored. A reproducible build script fetches the pinned upstream commit and applies the tracked GPL patch set. No binary is committed. | ESP32-S3 CPU and SoC emulation |
| Espressif QEMU ESP32-S3 GDB register map | Same pinned QEMU commit; `target/xtensa/core-esp32s3/gdb-config.inc.c` | Permissive Tensilica notice in that source file; compatible with this project | Source is not copied. Register names, numbers, and bit sizes 0 through 83 are represented in the service as a compatibility fallback because the target does not advertise feature XML. | Typed register inspection through the private GDB worker boundary |
| Espressif ESP32-S3 ROM image | From the pinned Espressif QEMU release | Separate Espressif terms; redistribution review pending | Not committed or redistributed. A local operator supplies an artifact obtained from Espressif. | First-stage boot ROM required by the QEMU machine |
| PlatformIO Espressif32 / Arduino-ESP32 | Platform `6.12.0`; Arduino-ESP32 `2.0.17` | Apache-2.0 and component-specific notices | Build dependency only; generated packages and firmware are not committed | Builds the simulator-owned conformance firmware |
| Texas Instruments TCA8418 documentation | TCA8418 datasheet, current design reference | TI documentation terms | Documentation is not copied or redistributed | Authoritative register and FIFO behavior for the original QEMU device model |
| Sitronix ST7789 documentation | Public ST7789 controller documentation | Sitronix documentation terms | Documentation is not copied or redistributed | Command, address-window, color-mode, and framebuffer behavior for the original QEMU device model |
| M5Stack hardware documentation | Cardputer ADV and StickS3 product documentation | M5Stack documentation terms | Documentation and product artwork are not copied or redistributed | Public pin assignments and visible display geometry |
| M5Stack M5GFX library | Local reference snapshot; upstream MIT project | MIT | Not vendored; no source code copied | Cross-checks public ST7789 offsets and firmware-visible initialization behavior |
| M5Stack M5Cardputer library | Reference commit `2d4fa6646e4e5b47e0af96214b003aa7b15b8d81` | MIT | Not vendored; no source code copied | Cross-checks public Cardputer keyboard layout and event remapping |
| Bosch BMI270 documentation | BMI270 datasheet, current design reference | Bosch Sensortec documentation terms | Documentation is not copied or redistributed | Authoritative device identity, register map, ranges, and sample encoding for the original behavioral model |
| M5Stack M5Unified and M5PM1 libraries | Local reference snapshots; upstream MIT projects | MIT | Not vendored; no source code copied | Cross-checks public StickS3 initialization sequences and M5PM1 register use |
| M5Stack device names | Cardputer ADV and StickS3 compatibility references | Third-party trademarks | Text compatibility references only; no official product artwork | Identifies target hardware profiles |
| React and React DOM | `19.2.7` | MIT | Installed from the pinned npm lockfile and bundled into the browser client | Browser UI runtime |
| Lucide React | `1.25.0` | ISC | Installed from the pinned npm lockfile; selected SVG components are bundled into the browser client | Interface iconography |
| Vite and `@vitejs/plugin-react` | `8.1.5` and `6.0.3` | MIT | Pinned npm build dependencies; not served as standalone runtime packages | Browser development server and release build |
| TypeScript and DefinitelyTyped packages | TypeScript `7.0.2`; types pinned in `web/package-lock.json` | Apache-2.0 and MIT | Pinned npm build dependencies; type declarations are not shipped as browser runtime code | Static browser-client validation |
| Vitest, Testing Library, and jsdom | Versions pinned in `web/package-lock.json` | MIT | Development and test dependencies only | Browser component and protocol-helper tests |
| Playwright Test | `1.61.1` | Apache-2.0 | Test dependency only; browser binaries are downloaded separately and are not committed | Rendered desktop and portrait browser verification |
| Bubblewrap | Deployment baseline `0.9.0` | LGPL-2.0-or-later | External host executable; source and binary are not vendored or committed | Per-worker Linux namespace and filesystem containment |

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
