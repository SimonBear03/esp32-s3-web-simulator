#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from esp32_s3_simulator.qemu import (
    DEFAULT_SANDBOX_READONLY_PATHS,
    QemuWorkerConfig,
    WorkerSandboxMode,
    wrap_worker_command,
)

PROBE = r"""
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

forbidden = json.loads(sys.argv[1])
marker = Path("sandbox-write-probe")
marker.write_text("private scratch only", encoding="utf-8")
status = Path("/proc/self/status").read_text(encoding="utf-8")
cap_eff = next(line.split()[1] for line in status.splitlines() if line.startswith("CapEff:"))
routes = Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]
nested_userns_returncode = subprocess.run(
    ["/usr/bin/unshare", "--user", "/usr/bin/true"],
    capture_output=True,
    check=False,
).returncode
secret_keys = [
    key for key in os.environ
    if any(part in key.upper() for part in ("SECRET", "TOKEN", "PASSWORD", "KEY"))
]
print(json.dumps({
    "cap_eff": cap_eff,
    "forbidden_visible": [path for path in forbidden if Path(path).exists()],
    "routes": routes,
    "scratch_write": marker.read_text(encoding="utf-8"),
    "secret_keys": secret_keys,
    "nested_userns_returncode": nested_userns_returncode,
}, sort_keys=True))
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe the Bubblewrap worker boundary")
    parser.add_argument("--sandbox-executable", type=Path, default=Path("/usr/bin/bwrap"))
    parser.add_argument(
        "--readonly-path",
        action="append",
        dest="readonly_paths",
        type=Path,
        help="read-only runtime path set (repeat; replaces the default set)",
    )
    parser.add_argument(
        "--forbidden-path",
        action="append",
        dest="forbidden_paths",
        default=["/home", "/root", "/var/run/docker.sock", "/run/docker.sock"],
        help="host path that must not exist inside the worker",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    readonly_paths = (
        tuple(path.absolute() for path in args.readonly_paths)
        if args.readonly_paths
        else DEFAULT_SANDBOX_READONLY_PATHS
    )
    config = QemuWorkerConfig(
        executable=Path("/usr/bin/python3"),
        rom_directory=Path("/usr"),
        sandbox_mode=WorkerSandboxMode.BUBBLEWRAP,
        sandbox_executable=args.sandbox_executable.absolute(),
        sandbox_readonly_paths=readonly_paths,
    )
    config.validate()
    with tempfile.TemporaryDirectory(prefix="esp32-sandbox-probe-") as scratch:
        command = wrap_worker_command(
            config,
            (
                "/usr/bin/python3",
                "-I",
                "-c",
                PROBE,
                json.dumps(args.forbidden_paths),
            ),
            Path(scratch),
        )
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            text=True,
            timeout=15,
        )
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    failures = []
    if result["cap_eff"] != "0000000000000000":
        failures.append(f"effective capabilities remain: {result['cap_eff']}")
    if result["forbidden_visible"]:
        failures.append(f"forbidden paths visible: {result['forbidden_visible']}")
    if result["routes"]:
        failures.append(f"network routes visible: {result['routes']}")
    if result["scratch_write"] != "private scratch only":
        failures.append("private scratch was not writable")
    if result["secret_keys"]:
        failures.append(f"secret-like environment keys visible: {result['secret_keys']}")
    if result["nested_userns_returncode"] == 0:
        failures.append("nested user namespaces remain enabled")
    if failures:
        raise SystemExit("sandbox probe failed: " + "; ".join(failures))
    print(json.dumps({"status": "passed", **result}, sort_keys=True))


if __name__ == "__main__":
    main()
