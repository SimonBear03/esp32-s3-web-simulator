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
code when known, non-secret firmware metadata, a monotonic `generation`, and
bounded recording/replay summaries. Generation `1` is the uploaded baseline;
each replay increments it after restoring that baseline.

Production workers enable private QMP and GDB Unix sockets for worker control.
`SIMULATOR_WORKER_QMP_ENABLED=false` exists only for constrained test sandboxes
that prohibit local socket binding; it is not a production configuration.
`SIMULATOR_WORKER_DEBUG_ENABLED=false` disables the GDB socket and typed debug
operations; debugging also requires QMP so run state can remain synchronized.
Neither private socket is part of the public protocol.

Session creation does not report `running` merely because a worker process was
spawned. The worker must answer private QMP `query-status` as running within
`SIMULATOR_WORKER_STARTUP_TIMEOUT_SECONDS`; the legitimate `prelaunch` state is
polled only until that bounded deadline. Invalid states, early exits, and QMP
failure terminate the worker and fail session creation. The configured runtime
root must also leave enough room for the opaque session directory and QMP/GDB
names within Linux's 107-byte Unix-socket path limit.

`GET /health/ready` reports `status`, `native_worker`, and
`worker_sandbox` (`direct` or `bubblewrap`). Production sets
`SIMULATOR_WORKER_SANDBOX_MODE=bubblewrap` is the controlled rollback boundary;
the hostile public deployment uses `oci-broker`. Readiness degrades if the
configured sandbox executable, broker socket, or any required read-only runtime
path is missing.
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

The workbench can optionally load the matching 32-bit little-endian Xtensa ELF
next to the required merged flash image. This is deliberately not an API
upload: the browser enforces a 32 MiB limit, parses a bounded executable symbol
table, and retains only its in-memory index for the active page/session. Pasted
panic/backtrace addresses and the paused program counter can then be resolved
to function-plus-offset locally. The ELF does not enter multipart session
creation, saved-app storage, diagnostics, replay, gateway logs, or backups.

If the guest reaches a breakpoint after resume, its state changes back to
`paused` and `debug/status` reports the stop reply. Clients should poll session
or debug status until the later event-stream protocol is implemented.

## Timeline and diagnostics

`GET /v1/sessions/{id}/events` returns the session's bounded typed event
timeline. The optional `after` cursor is an event sequence and `limit` is capped
by `SIMULATOR_MAX_EVENT_PAGE_SIZE` (500 by default). The response reports when
older events or the requested cursor were truncated. Events contain generation,
monotonic offset, category, type, source, and bounded structured metadata.

The service records accepted external inputs, reset/pause/resume controls,
replay lifecycle, worker lifecycle, and native allowlisted peripheral events.
The current QEMU worker emits SPI transaction summaries, I2C bus activity,
GPIO transitions, ST7789 commands/windows, keyboard or button transitions, IMU
samples, power state, and ADC conversions. Repetitive trace sources are sampled
at deterministic per-source limits so boot-time bus traffic cannot crowd later
interactive events out of the global generation bound. A typed sampling marker
records when this happens. UART input appears only as a byte count and SHA-256
digest; its contents are never present in the public timeline.
`SIMULATOR_MAX_RECORDING_EVENTS` bounds both public events and replayable input
actions (4096 each by default). Replay fails closed if the input-action bound
was exceeded, because silently replaying an incomplete recording would be
misleading.

`GET /v1/sessions/{id}/diagnostics` downloads
`esp32-s3-simulator-diagnostics/v1` JSON. It contains session and worker
metadata, firmware hashes, replay status, the bounded timeline, and redacted
serial byte statistics. It excludes uploaded firmware bytes, mutated
flash/NVS, framebuffer pixels, debug memory data, and UART payloads.

## External-input replay

`POST /v1/sessions/{id}/replay` accepts `{"speed":1}` where speed is between
0.25 and 4. The operation is asynchronous; `GET /v1/sessions/{id}/replay` and
normal session polling expose status. A replay:

1. stops the private worker;
2. overwrites its flash with the in-memory, original normalized upload;
3. starts a new worker generation;
4. reapplies accepted key, button, IMU, power, UART-input, and reset actions at
   their recorded monotonic offsets.

Pause/resume and debug operations are observations or execution controls, not
external board stimuli, so they are present in the timeline but excluded from
the replay program. Live input is rejected while replay runs. This is
deterministic external-input replay against the same simulator build and board
model; it is not a claim of instruction-level determinism, simulated network
determinism, or physical/electrical certification. Replays are bounded by
`SIMULATOR_MAX_REPLAY_DURATION_SECONDS` (120 seconds by default).

## Pending protocol surfaces

Instruction/timing traces, DWARF source file/line decoding, C++ demangling, and
CPU-state rewind remain pending. They are not represented as fake-success
events until their execution and privacy contracts exist.
