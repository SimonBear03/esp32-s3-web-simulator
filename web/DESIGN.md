# Browser workbench design system

The browser client is a precision-instrument workbench, not a marketing page.
Its four stable regions are firmware setup, the virtual device stage, the
runtime inspector, and the serial dock.

## Tokens

- Background: true graphite `#0b0e10`; open work surface `#10161a`; raised
  surface `#151c20`.
- Text: warm white `#f1f2ed`; secondary `#9ea7aa`; technical muted `#737e82`.
- Accent: signal lime `#a7db36`; paused amber `#f2ad32`; destructive red
  `#e66b62`.
- Structure: cool gray borders `#2a353a`, one pixel; 8 and 12 pixel radii;
  shallow black shadows only.
- Typography: a modern system grotesk for product chrome and a compact system
  monospace for firmware values, registers, memory, and serial.
- Motion: 140 ms control feedback and a restrained running-state pulse, both
  disabled by `prefers-reduced-motion`.

## Components and responsive rules

- `AppHeader` owns board selection, authoritative run state, and session
  controls.
- `FirmwarePanel` performs accurate local merged-image checks and starts the
  real API session. Its optional matching ELF control indexes bounded Xtensa
  function symbols locally, verifies the ESP-IDF application build hash when
  available, and never adds the ELF to a network request.
- `DeviceStage` owns the original compatible-device shells and a canvas-backed
  RGB framebuffer. The Cardputer keyboard and StickS3 buttons remain native
  buttons.
- `Inspector` owns typed board inputs, browser-only backtrace symbolication, and
  bounded debugger controls. It never exposes raw QMP or GDB.
- `SerialDock` owns the bounded UART transcript, command input, and a compact
  browser-derived strip for function addresses found in the recent UART tail.
- At desktop widths the workbench is a three-column open grid above a docked
  serial region. At narrow widths setup becomes a disclosure and Device,
  Serial, and Inspector become mutually exclusive primary panels.
- Hosted access is an optional full-workbench gate, not a marketing surface.
  It uses the existing graphite/lime instrument language, states the exact
  ephemeral-retention boundary, and unlocks only after the server issues an
  HttpOnly capability. It is absent in standalone mode.

The generated visual concepts are design references only and are not shipped
as product assets. Device shells are original CSS/HTML constructions and do not
copy official product artwork or branding.
