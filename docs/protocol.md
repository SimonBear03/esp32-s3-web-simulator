# Simulator API protocol

The public protocol is versioned under `/v1`. It is intentionally independent
of QEMU so another engine, including a future WebAssembly worker, can implement
the same browser-facing contract.

## Board discovery

`GET /v1/boards` returns the board profiles and an explicit fidelity claim for
each capability. `emulated` means an implemented execution path exists;
`behavioral` means a deterministic logical model exists; `planned` means the
surface is visible but not yet implemented; `unsupported` means the simulator
does not claim it.

## Session creation

`POST /v1/sessions` accepts multipart fields:

- `board_id`: `cardputer-adv` or `sticks3`;
- `firmware`: a merged ESP32-S3 flash image whose byte zero maps to flash
  offset zero.

The service validates the ESP image header, enforces the board flash capacity,
pads the private worker copy with erased `0xFF` bytes, records content hashes,
and never returns or persists the upload beyond the session runtime directory.
ELF loading will be a separate explicit mode; an ELF is not silently treated as
a flash image.

The response includes an opaque session ID, board ID, timestamps, state, exit
code when known, and non-secret firmware metadata.

Production workers enable a private QMP Unix socket for control and debugging.
`SIMULATOR_WORKER_QMP_ENABLED=false` exists only for constrained test sandboxes
that prohibit local socket binding; it is not a production configuration.

## Session state

- `GET /v1/sessions/{id}` returns current state.
- `DELETE /v1/sessions/{id}` stops the worker and destroys its runtime files.
- Sessions expire automatically at the configured TTL.

## Serial stream

`WS /v1/sessions/{id}/serial` carries binary UART chunks in both directions.
The server replays a bounded recent-output buffer when a debugger connects.
UART is a byte stream: clients must not assume each WebSocket message is a full
line.

## Board input

`WS /v1/sessions/{id}/input` accepts typed JSON events. The first implemented
event is a Cardputer ADV key transition:

```json
{"type":"key","key":"a","pressed":true,"sequence":17}
```

The service responds with `{"type":"ack","sequence":17}` only after QMP
accepts the event. Invalid, unsupported, or unavailable inputs produce a typed
`error` response. Valid key identifiers are the four physical keyboard rows:

- `grave`, `0` through `9`, `minus`, `equals`, `backspace`;
- `tab`, `q` through `p`, `bracket-left`, `bracket-right`, `backslash`;
- `fn`, `shift`, `a` through `l`, `semicolon`, `apostrophe`, `enter`;
- `ctrl`, `opt`, `alt`, `z` through `m`, `comma`, `period`, `slash`, `space`.

These are board-level identifiers. QEMU key names and the Cardputer matrix
encoding are private worker details.

## Pending protocol surfaces

Framebuffer updates, StickS3 button input, power events, QMP-backed pause/reset,
breakpoints, memory inspection, and deterministic traces will use distinct
typed WebSocket messages. They are not represented as fake-success endpoints
until their worker implementations exist.
