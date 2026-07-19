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
write operation.

The private deployment site is responsible for authentication, ownership,
CSRF/origin policy, per-user quotas, rate limits, and keeping opaque session IDs
bound to the account that created them. The public core service must not be
exposed directly to the internet without that gateway or equivalent controls.

## Worker controls already enforced

- guest networking is disabled;
- one subprocess is created per session with address-space, CPU-time, file-size,
  and file-descriptor limits;
- firmware size and image headers are checked before launch;
- concurrency and TTL are bounded;
- flash/NVS, sockets, screenshots, and uploads live only in the private session
  directory and are removed when the session stops;
- firmware bytes are excluded from public metadata and diagnostics.

## Production isolation gate

Process resource limits are defense in depth, not a complete hostile-code
sandbox. The service now provides a production Bubblewrap worker mode that:

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

Before an internet deployment accepts arbitrary public firmware, the worker
must use that mode or an equivalent OS sandbox, and the containing service must
also provide:

- cgroup CPU, memory, process, and wall-clock limits;
- a minimal syscall/device policy such as seccomp plus AppArmor or an
  equivalent confinement layer;
- automatic kill and cleanup independent of the API process;
- upload, request, WebSocket, session, and account-level rate limits;
- structured security logs that never contain firmware or secret values.

The deployment should fail closed when any required isolation mechanism is
absent. Direct worker mode is suitable for controlled local development, not
public hostile workloads. Bubblewrap reduces filesystem, network, capability,
and cross-session authority but still shares the host kernel; patch management,
conservative quotas, monitoring, and the outer service sandbox remain required.

## Data retention

The default contract is ephemeral: uploaded firmware and mutated flash/NVS are
destroyed with the session. Any future save-state or downloadable-diagnostics
feature must be explicit, access-controlled, size-bounded, and must exclude the
uploaded firmware by default.

QEMU documents the GDB stub's lack of authentication and recommends securing
its endpoint separately: <https://www.qemu.org/docs/master/system/gdb.html>.
