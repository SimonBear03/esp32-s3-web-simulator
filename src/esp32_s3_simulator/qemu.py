# SPDX-License-Identifier: GPL-2.0-only

from dataclasses import dataclass
from pathlib import Path

from .boards import BoardProfile


@dataclass(frozen=True, slots=True)
class QemuWorkerConfig:
    executable: Path
    rom_directory: Path

    def validate(self) -> None:
        if not self.executable.is_file():
            raise FileNotFoundError(f"QEMU executable not found: {self.executable}")
        if not self.rom_directory.is_dir():
            raise FileNotFoundError(f"QEMU ROM directory not found: {self.rom_directory}")


def build_qemu_command(
    config: QemuWorkerConfig,
    board: BoardProfile,
    flash_path: Path,
    qmp_socket_path: Path | None,
) -> tuple[str, ...]:
    command = [
        str(config.executable),
        "-L",
        str(config.rom_directory),
        "-M",
        "esp32s3",
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
    if board.psram_size_mib:
        command.extend(("-m", f"{board.psram_size_mib}M"))
    command.extend(("-drive", f"file={flash_path},if=mtd,format=raw"))
    return tuple(command)
