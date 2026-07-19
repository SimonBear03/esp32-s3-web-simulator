# SPDX-License-Identifier: GPL-2.0-only

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .boards import BoardProfile
from .tracing import TRACE_EVENT_NAMES


class WorkerSandboxMode(StrEnum):
    DIRECT = "direct"
    BUBBLEWRAP = "bubblewrap"


DEFAULT_SANDBOX_READONLY_PATHS = (
    Path("/usr"),
    Path("/lib"),
    Path("/lib64"),
)


@dataclass(frozen=True, slots=True)
class QemuWorkerConfig:
    executable: Path
    rom_directory: Path
    sandbox_mode: WorkerSandboxMode = WorkerSandboxMode.DIRECT
    sandbox_executable: Path = Path("/usr/bin/bwrap")
    sandbox_readonly_paths: tuple[Path, ...] = DEFAULT_SANDBOX_READONLY_PATHS

    def validate(self) -> None:
        if not self.executable.is_file() or not os.access(self.executable, os.X_OK):
            raise FileNotFoundError(f"QEMU executable not found: {self.executable}")
        if not self.rom_directory.is_dir():
            raise FileNotFoundError(f"QEMU ROM directory not found: {self.rom_directory}")
        if self.sandbox_mode is WorkerSandboxMode.BUBBLEWRAP:
            if not self.sandbox_executable.is_file() or not os.access(
                self.sandbox_executable, os.X_OK
            ):
                raise FileNotFoundError(
                    f"Bubblewrap executable not found: {self.sandbox_executable}"
                )
            missing = [path for path in self.sandbox_readonly_paths if not path.exists()]
            if missing:
                raise FileNotFoundError(
                    "Bubblewrap read-only path not found: "
                    + ", ".join(str(path) for path in missing)
                )


def _direct_qemu_command(
    config: QemuWorkerConfig,
    board: BoardProfile,
    flash_path: Path,
    qmp_socket_path: Path | None,
    gdb_socket_path: Path | None,
    trace_enabled: bool,
) -> tuple[str, ...]:
    command = [
        str(config.executable),
        "-L",
        str(config.rom_directory),
        "-M",
        f"esp32s3,board-profile={board.id}",
        "-nographic",
        "-nic",
        "none",
        "-monitor",
        "none",
        "-serial",
        "stdio",
    ]
    if qmp_socket_path is not None:
        command.extend(("-qmp", f"unix:{qmp_socket_path},server=on,wait=off"))
    if gdb_socket_path is not None:
        command.extend(
            (
                "-chardev",
                f"socket,path={gdb_socket_path},server=on,wait=off,id=gdb0",
                "-gdb",
                "chardev:gdb0",
            )
        )
    if trace_enabled:
        for event_name in TRACE_EVENT_NAMES:
            command.extend(("-trace", f"enable={event_name}"))
        command.extend(("-trace", "file=/dev/stderr"))
    if board.psram_size_mib:
        command.extend(("-m", f"{board.psram_size_mib}M"))
    command.extend(("-drive", f"file={flash_path},if=mtd,format=raw"))
    return tuple(command)


def _session_directory(
    flash_path: Path,
    qmp_socket_path: Path | None,
    gdb_socket_path: Path | None,
) -> Path:
    directory = flash_path.parent
    private_paths = [path for path in (qmp_socket_path, gdb_socket_path) if path]
    if any(path.parent != directory for path in private_paths):
        raise ValueError("worker flash and control sockets must share one session directory")
    return directory


def wrap_worker_command(
    config: QemuWorkerConfig,
    worker_command: tuple[str, ...],
    session_directory: Path,
) -> tuple[str, ...]:
    command = [
        str(config.sandbox_executable),
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--unshare-user",
        "--disable-userns",
        "--hostname",
        "esp32-s3-worker",
        "--cap-drop",
        "ALL",
        "--clearenv",
        "--setenv",
        "LANG",
        "C.UTF-8",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--size",
        str(16 * 1024 * 1024),
        "--tmpfs",
        "/tmp",
    ]
    mounted_paths: set[Path] = set()
    for path in (
        *config.sandbox_readonly_paths,
        config.executable.parent,
        config.rom_directory,
    ):
        destination = path.absolute()
        if any(destination.is_relative_to(mounted) for mounted in mounted_paths):
            continue
        mounted_paths.add(destination)
        command.extend(("--ro-bind", str(destination), str(destination)))
    command.extend(
        (
            "--bind",
            str(session_directory),
            str(session_directory),
            "--chdir",
            str(session_directory),
            "--",
            *worker_command,
        )
    )
    return tuple(command)


def build_qemu_command(
    config: QemuWorkerConfig,
    board: BoardProfile,
    flash_path: Path,
    qmp_socket_path: Path | None,
    gdb_socket_path: Path | None,
    *,
    trace_enabled: bool = False,
) -> tuple[str, ...]:
    qemu_command = _direct_qemu_command(
        config,
        board,
        flash_path,
        qmp_socket_path,
        gdb_socket_path,
        trace_enabled,
    )
    if config.sandbox_mode is WorkerSandboxMode.DIRECT:
        return qemu_command
    return wrap_worker_command(
        config,
        qemu_command,
        _session_directory(flash_path, qmp_socket_path, gdb_socket_path),
    )
