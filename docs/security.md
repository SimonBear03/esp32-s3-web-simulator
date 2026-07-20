# Security boundary

Uploaded firmware is untrusted code. The simulator must assume a crafted image
will try to crash QEMU, exhaust resources, probe the host, retain data, or abuse
every control channel available to it.

## Public and private surfaces

The versioned HTTP and WebSocket API is the only browser-facing simulator
surface. QMP, GDB, worker stdio, runtime paths, and emulator command lines are
private implementation details. In particular, QEMU's GDB server has no
authentication and can control guest execution; it must never listen on TCP or
be reverse-proxied to a client.

Each worker receives QMP and GDB Unix sockets under its opaque session
directory. The runtime root and child process use owner-only permissions and a
`077` umask. The GDB adapter permits only register reads, memory reads bounded to
4096 bytes, 32 hardware breakpoints, continue through session resume, and
single-step while paused. It has no raw-command tunnel and no register or memory
write operation. Startup rejects a runtime root whose opaque session directory
and socket filenames would exceed Linux's 107-byte Unix-socket path limit;
sessions are never exposed as running before QMP confirms a live worker.

The private deployment site is responsible for authentication, ownership,
CSRF/origin policy, per-user quotas, rate limits, and keeping opaque session IDs
bound to the account that created them. The public core service must not be
exposed directly to the internet without that gateway or equivalent controls.

For optional Supabase account access, the browser receives only the project URL
and publishable key. It sends the current access token to the same-origin
gateway once for exchange; a peer-credential-gated verifier with no database,
firmware, storage-key, worker, or Docker access validates it against the fixed
Supabase user endpoint. The gateway stores only a stable owner mapping and hash
of its own short-lived HttpOnly cookie, never the Supabase access or refresh
token. Local password mode is a development facility and is refused by the
production gateway configuration.

For optional anonymous access, the browser receives only a public Turnstile
site key. The gateway validates a single-use token through a separate,
peer-credential-gated verifier process that alone holds the secret and internet
egress. The main site retains loopback-only network policy. Anonymous
capabilities are random HttpOnly, Secure, SameSite=Strict cookies; only their
hashes and keyed-HMAC client scopes are stored. The gateway binds every
operation and WebSocket to the capability, admits one active session per
browser/network, shares the global account capacity atomically, and limits both
challenge attempts and creation events. Cloudflare's connecting-IP header is
trusted only when the immediate peer belongs to Cloudflare's published edge
networks.

Anonymous sessions have a deployment hard lifetime, require a periodic browser
heartbeat, cannot be revived after inactivity, and are deleted by an
independent reconciliation loop. The hosted anonymous surface omits debugger,
diagnostics, and replay routes; signed-in accounts retain the full bounded
worker tooling. A browser-only ELF decoder may still appear for an anonymous
session because it sends neither the ELF nor decoded addresses to the gateway
or core. Browser parsing rejects ELF files above 32 MiB, symbol tables above
100000 entries, malformed bounds, and firmware build-match inputs above the
board's 8 MiB capacity. Anonymous access stays disabled unless the verifier,
OCI broker, core, and static workbench all pass readiness.

Optional saved-app storage belongs to the private gateway, not this public core.
The public client renders it only for a gateway-confirmed account, keeps save
separate from run, and cannot access storage encryption keys or paths. The
gateway must enforce ownership and its ten-slot limit independently of the UI,
encrypt firmware at rest with authenticated metadata, and copy a decrypted slot
only into a fresh ephemeral worker. Anonymous and ordinary-upload firmware must
remain excluded from that store and its backups.

## Worker controls already enforced

- guest networking is disabled;
- one subprocess is created per session with address-space, CPU-time, file-size,
  and file-descriptor limits;
- firmware size and image headers are checked before launch;
- concurrency and TTL are bounded;
- flash/NVS, sockets, screenshots, and uploads live only in the private session
  directory and are removed when the session stops;
- powering off removes the worker, sockets, screenshots, streams, and
  RAM-adjacent service state but deliberately retains the private flash/NVS
  image until power on, explicit stop, expiry, or failure;
- firmware bytes are excluded from public metadata and diagnostics.

## Production isolation gate

Process resource limits are defense in depth, not a complete hostile-code
sandbox. Bubblewrap remains available for controlled authenticated testing and
rollback, but it is not the selected anonymous-internet boundary.

The selected production design is the dedicated rootless OCI worker broker
documented in [worker-isolation.md](worker-isolation.md). It keeps all Docker
authority out of the API and gateway identities and applies an immutable image,
outer seccomp/AppArmor, namespaces, cgroups, no network, a read-only root,
capability removal, a single validated session bind, QEMU's inner seccomp
sandbox, independent wall time, bounded I/O, and reconciliation. It fails closed
instead of falling back when any required control is unavailable.

The service also provides a Bubblewrap worker mode that:

- creates new user, PID, IPC, UTS, cgroup, and network namespaces;
- disables nested user namespaces and drops every effective capability;
- clears the environment and exposes no host network routes;
- mounts configured runtime libraries, the QEMU executable directory, and ROM
  directory read-only;
- provides a 16 MiB temporary filesystem and binds only the current session
  directory writable;
- fails worker readiness closed when the sandbox executable or a configured
  read-only input is absent.

The owned Cardputer ADV and StickS3 conformance suites pass boot, display,
input, NVS, reset, debugger, and cleanup inside that boundary. The automated
denial probe separately verifies zero capabilities, no host routes, hidden host
paths, a cleared secret-like environment, disabled nested user namespaces, and
writable private scratch.

Before an internet deployment accepts arbitrary public firmware, the live
rootless OCI boundary and containing service must prove:

- cgroup CPU, memory, process, and wall-clock limits;
- a minimal syscall/device policy such as seccomp plus AppArmor or an
  equivalent confinement layer;
- automatic kill and cleanup independent of the API process;
- upload, request, WebSocket, session, and account-level rate limits;
- server-side challenge validation with exact hostname, action, and freshness;
- anonymous heartbeat, hard-expiry, and abandoned-session cleanup;
- structured security logs that never contain firmware or secret values.

Direct worker mode is suitable for controlled local development, not public
hostile workloads. Bubblewrap reduces filesystem, network, capability, and
cross-session authority but still shares the host kernel and is not an
automatic availability fallback for anonymous sessions.

## Data retention

The default contract is ephemeral: uploaded firmware, its in-memory replay
baseline, recorded UART payloads, and mutated flash/NVS are destroyed with the
session. `powered_off` is an active retained state rather than destruction: it
continues to consume a session slot and TTL, and anonymous hosting continues to
require heartbeats and inactivity cleanup. An optional symbol ELF has a
stricter boundary: it is parsed in the
browser, is never uploaded, and its in-memory index is dropped when the session
ends or the page closes. Diagnostics are explicit, access-controlled by the
hosting gateway, size-bounded, and exclude firmware, mutated flash, framebuffer pixels, debug
memory, and UART payloads. The replay baseline and private UART actions never
cross the public API.

A hosting gateway may offer an explicit account-only saved copy as a separate
product feature. That exception does not change the core's lifecycle: every
core worker, mutated flash/NVS, UART stream, framebuffer, and replay baseline
remain ephemeral, and deleting a worker never writes them back into a saved
slot.

QEMU documents the GDB stub's lack of authentication and recommends securing
its endpoint separately: <https://www.qemu.org/docs/master/system/gdb.html>.
