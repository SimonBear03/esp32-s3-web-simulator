# Rootless OCI worker boundary

Anonymous internet firmware is hostile input. Production uses a dedicated
rootless Docker daemon behind `esp32-s3-worker-broker`; the API process never
receives either a rootful or rootless Docker socket.

The broker accepts a versioned, length-bounded local protocol over an
owner/group-restricted Unix socket. Linux `SO_PEERCRED` must identify the one
configured core-service UID. A client may only ping the broker, start one
validated opaque session and owned board profile, relay bounded UART bytes, or
stop that same worker. It cannot select an image, command, mount, environment,
network, device, capability, security profile, label, resource value, or Docker
operation.

The broker derives every launch from typed operator configuration. Production
startup fails unless the Docker endpoint is the broker identity's own
`/run/user/<uid>/docker.sock`, Docker reports rootless mode, seccomp and cgroup
v2, the image is addressed by an immutable SHA-256 digest, the custom seccomp
profile is a protected regular file, the core and broker use different UIDs,
and every runtime path has exact core/shared-group ownership with no access for
other users.

Each worker has:

- no OCI network or IPC namespace sharing;
- a read-only root filesystem and one validated writable session bind;
- all capabilities dropped and `no-new-privileges` enabled;
- operator-installed seccomp and AppArmor profiles;
- fixed memory, swap, CPU, PID, file-size, descriptor, tmpfs and wall-time
  limits;
- an immutable image with SLiRP compiled out and QEMU's own restrictive
  seccomp sandbox enabled;
- no host repository, credential, Docker socket, device or unrelated runtime
  mount;
- bounded broker output, disconnect cleanup, startup reconciliation and a
  periodic runtime health check.

Readiness probes the broker instead of merely checking that a socket pathname
exists. A broker or runtime health failure disables new sessions; there is no
automatic fallback to Bubblewrap or direct execution.

## Image build and ROM boundary

`scripts/build-worker-image.sh` accepts only digest-pinned build/runtime base
images and uses the dedicated rootless Docker endpoint explicitly. It builds
the pinned Espressif QEMU commit with the public patch stack, SLiRP disabled and
libseccomp enabled, then returns the immutable local image ID.

The ESP32-S3 boot ROM is intentionally absent from Git and from the public
build context. An operator must supply a reviewed, non-symlink ROM file and its
expected SHA-256 through a separate BuildKit context. Do not publish a worker
image containing that ROM until its redistribution terms have been reviewed.
The QEMU source, patches and corresponding-source obligations remain covered by
the repository's GPL documentation.

## Deployment acceptance gate

Code-level controls are not proof that the host enforces them. Before anonymous
execution is enabled, deployment tests must inspect the live container and
cgroup, prove the seccomp/AppArmor profiles are active, verify no network or
Docker socket is reachable, exercise resource exhaustion and crash cleanup,
run both owned board conformance suites, and verify unrelated VPS services
retain headroom with two worst-case workers. Anonymous creation remains disabled
when any check is unavailable or fails.

The host gate must additionally prove the isolated Turnstile verifier has no
site database, core, broker, worker, or Docker access; the site has no general
internet egress; anonymous capability/session quotas serialize across accounts;
and a lost heartbeat deletes the managed worker within the documented cleanup
window.
