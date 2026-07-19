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

Production workers enable private QMP and GDB Unix sockets for worker control.
`SIMULATOR_WORKER_QMP_ENABLED=false` exists only for constrained test sandboxes
that prohibit local socket binding; it is not a production configuration.
`SIMULATOR_WORKER_DEBUG_ENABLED=false` disables the GDB socket and typed debug
operations; debugging also requires QMP so run state can remain synchronized.
Neither private socket is part of the public protocol.

`GET /health/ready` reports `status`, `native_worker`, and
`worker_sandbox` (`direct` or `bubblewrap`). Production sets
`SIMULATOR_WORKER_SANDBOX_MODE=bubblewrap`; readiness degrades if the configured
Bubblewrap executable or any required read-only runtime path is missing.
`SIMULATOR_WORKER_SANDBOX_READONLY_PATHS` is a colon-separated allow-list for
the dynamic runtime and packaged QEMU dependencies. The worker executable
directory and ROM directory are added automatically, while only the current
session directory is writable.

## Session state

- `GET /v1/sessions/{id}` returns current state.
- `DELETE /v1/sessions/{id}` stops the worker and destroys its runtime files.
- `POST /v1/sessions/{id}/control` accepts one of
  `{"action":"pause"}`, `{"action":"resume"}`, or `{"action":"reset"}`.
  Pause and resume map to QEMU execution control; reset preserves the private
  flash/NVS image.
- Sessions expire automatically at the configured TTL.

## Serial stream

`WS /v1/sessions/{id}/serial` carries binary UART chunks in both directions.
The server replays a bounded recent-output buffer when a debugger connects.
UART is a byte stream: clients must not assume each WebSocket message is a full
line.

## Framebuffer stream

`WS /v1/sessions/{id}/framebuffer` sends changed RGB24 frames as binary
messages. Capture is demand-driven and bounded by
`SIMULATOR_FRAMEBUFFER_INTERVAL_MS` (100 ms by default); a slow browser applies
backpressure directly and cannot create an unbounded server queue. Unchanged
frames are not resent.

Each message begins with this 14-byte, network-byte-order header, followed by
exactly `width * height * 3` row-major RGB bytes:

| Offset | Size | Field |
| --- | --- | --- |
| 0 | 4 | ASCII magic `ESPF` |
| 4 | 1 | protocol version, currently `1` |
| 5 | 1 | pixel format, `1` for RGB24 |
| 6 | 2 | width |
| 8 | 2 | height |
| 10 | 4 | frame sequence, wrapping uint32 |

## Board input

`WS /v1/sessions/{id}/input` accepts typed JSON events. Cardputer ADV key
transitions use:

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

The profiles accept these additional event types:

```json
{"type":"button","button":"a","pressed":true,"sequence":18}
{"type":"imu","acceleration_g":{"x":0,"y":0,"z":1},"angular_velocity_dps":{"x":0,"y":0,"z":0},"sequence":19}
{"type":"power","battery_mv":3900,"vin_mv":5000,"charging":true,"sequence":20}
```

Buttons `a` and `b` are StickS3-only and map to its active-low GPIO 11 and 12
inputs. Both profiles accept finite IMU units bounded to 16 g and 2000 dps;
their behavioral BMI270 converts samples according to firmware-selected range
registers. StickS3 power values are bounded to 0–6000 mV and reach firmware
through behavioral M5PM1 registers.

Cardputer ADV also accepts `power`, but only `battery_mv` represents real
hardware telemetry; clients must send `vin_mv: 0` and `charging: false` because
the board exposes neither value. The worker applies the physical 2:1 divider
and firmware reads the result through ADC1 channel 9 on GPIO10. An
acknowledgement means QEMU accepted the transition, not that analog or
electrical behavior has been certified.

## Debugger

Debugger operations require a paused session. Clients pause and resume with the
normal session-control endpoint, then use:

- `GET /v1/sessions/{id}/debug/status` for run state, the last GDB stop reply,
  and the exact capability limits;
- `GET /v1/sessions/{id}/debug/registers` for the ESP32-S3 Xtensa core-register
  snapshot;
- `POST /v1/sessions/{id}/debug/memory` with an unsigned 32-bit `address` and a
  `length` from 1 through 4096;
- `POST /v1/sessions/{id}/debug/breakpoint` with an unsigned 32-bit `address`
  and boolean `enabled` value;
- `POST /v1/sessions/{id}/debug/step` to execute one guest instruction and
  return its GDB stop reply.

Memory data is returned as lowercase hexadecimal in `data_hex`. A session may
hold at most 32 hardware breakpoints. Register or memory writes, arbitrary GDB
packets, monitor commands, and raw QMP are deliberately absent. QEMU's
unauthenticated GDB endpoint is attached only to a Unix socket inside the
private session directory; the service translates this bounded API instead of
exposing or tunnelling that socket.

If the guest reaches a breakpoint after resume, its state changes back to
`paused` and `debug/status` reports the stop reply. Clients should poll session
or debug status until the later event-stream protocol is implemented.

## Pending protocol surfaces

Deterministic peripheral traces remain pending. They are not represented as
fake-success endpoints until their worker implementations exist.
