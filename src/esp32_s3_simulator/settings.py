# SPDX-License-Identifier: GPL-2.0-only

import os
from dataclasses import dataclass
from pathlib import Path

from .qemu import DEFAULT_SANDBOX_READONLY_PATHS, WorkerSandboxMode


def _read_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    runtime_root: Path
    qemu_executable: Path
    rom_directory: Path
    native_workers_enabled: bool = False
    worker_qmp_enabled: bool = True
    worker_debug_enabled: bool = True
    worker_sandbox_mode: WorkerSandboxMode = WorkerSandboxMode.DIRECT
    worker_sandbox_executable: Path = Path("/usr/bin/bwrap")
    worker_sandbox_readonly_paths: tuple[Path, ...] = DEFAULT_SANDBOX_READONLY_PATHS
    max_concurrent_sessions: int = 2
    session_ttl_seconds: int = 120
    worker_memory_limit_mib: int = 1536
    worker_cpu_limit_seconds: int = 90
    framebuffer_interval_ms: int = 100

    @classmethod
    def from_environment(cls) -> "Settings":
        project_root = Path(__file__).resolve().parents[2]
        return cls(
            runtime_root=Path(
                os.environ.get("SIMULATOR_RUNTIME_ROOT", project_root / ".runtime")
            ).resolve(),
            qemu_executable=Path(
                os.environ.get(
                    "SIMULATOR_QEMU_EXECUTABLE",
                    project_root / ".cache/qemu/source/build/qemu-system-xtensa",
                )
            ).resolve(),
            rom_directory=Path(
                os.environ.get(
                    "SIMULATOR_QEMU_ROM_DIRECTORY", project_root / ".cache/qemu/source/pc-bios"
                )
            ).resolve(),
            native_workers_enabled=_read_bool("SIMULATOR_NATIVE_WORKERS_ENABLED", False),
            worker_qmp_enabled=_read_bool("SIMULATOR_WORKER_QMP_ENABLED", True),
            worker_debug_enabled=_read_bool("SIMULATOR_WORKER_DEBUG_ENABLED", True),
            worker_sandbox_mode=WorkerSandboxMode(
                os.environ.get("SIMULATOR_WORKER_SANDBOX_MODE", "direct")
            ),
            worker_sandbox_executable=Path(
                os.environ.get("SIMULATOR_WORKER_SANDBOX_EXECUTABLE", "/usr/bin/bwrap")
            ).resolve(),
            worker_sandbox_readonly_paths=tuple(
                Path(path).absolute()
                for path in os.environ.get(
                    "SIMULATOR_WORKER_SANDBOX_READONLY_PATHS",
                    "/usr:/lib:/lib64",
                ).split(":")
                if path
            ),
            max_concurrent_sessions=int(os.environ.get("SIMULATOR_MAX_SESSIONS", "2")),
            session_ttl_seconds=int(os.environ.get("SIMULATOR_SESSION_TTL_SECONDS", "120")),
            worker_memory_limit_mib=int(
                os.environ.get("SIMULATOR_WORKER_MEMORY_LIMIT_MIB", "1536")
            ),
            worker_cpu_limit_seconds=int(
                os.environ.get("SIMULATOR_WORKER_CPU_LIMIT_SECONDS", "90")
            ),
            framebuffer_interval_ms=int(
                os.environ.get("SIMULATOR_FRAMEBUFFER_INTERVAL_MS", "100")
            ),
        )
