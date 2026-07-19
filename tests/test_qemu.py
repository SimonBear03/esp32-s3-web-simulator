# SPDX-License-Identifier: GPL-2.0-only

from pathlib import Path

import pytest

from esp32_s3_simulator.boards import CARDPUTER_ADV, STICKS3
from esp32_s3_simulator.qemu import (
    QemuWorkerConfig,
    WorkerSandboxMode,
    build_qemu_command,
)


def command_for(board_id: str) -> tuple[str, ...]:
    board = CARDPUTER_ADV if board_id == CARDPUTER_ADV.id else STICKS3
    return build_qemu_command(
        QemuWorkerConfig(Path("/opt/qemu"), Path("/opt/roms")),
        board,
        Path("/runtime/flash.bin"),
        Path("/runtime/qmp.sock"),
        Path("/runtime/gdb.sock"),
        trace_enabled=True,
    )


def test_worker_command_disables_network_and_exposes_qmp_and_serial() -> None:
    command = command_for("cardputer-adv")

    assert command[:5] == (
        "/opt/qemu",
        "-L",
        "/opt/roms",
        "-M",
        "esp32s3,board-profile=cardputer-adv",
    )
    assert command[command.index("-nic") + 1] == "none"
    assert command[command.index("-serial") + 1] == "stdio"
    assert command[command.index("-monitor") + 1] == "none"
    assert command[command.index("-qmp") + 1].startswith("unix:/runtime/qmp.sock")
    assert command[command.index("-gdb") + 1] == "chardev:gdb0"
    assert "path=/runtime/gdb.sock" in command[command.index("-chardev") + 1]
    assert "-no-reboot" not in command
    assert "-m" not in command
    trace_options = [
        command[index + 1]
        for index, value in enumerate(command)
        if value == "-trace"
    ]
    assert "enable=esp32s3_gpspi_transaction" in trace_options
    assert "enable=i2c_send" in trace_options
    assert trace_options[-1] == "file=/dev/stderr"


def test_sticks3_worker_enables_eight_mebibytes_of_psram() -> None:
    command = command_for("sticks3")
    assert command[command.index("-M") + 1] == "esp32s3,board-profile=sticks3"
    assert command[command.index("-m") + 1] == "8M"


def test_qmp_can_be_disabled_for_restricted_test_sandboxes() -> None:
    command = build_qemu_command(
        QemuWorkerConfig(Path("/opt/qemu"), Path("/opt/roms")),
        CARDPUTER_ADV,
        Path("/runtime/flash.bin"),
        None,
        None,
    )
    assert "-qmp" not in command
    assert "-gdb" not in command


def test_bubblewrap_worker_gets_private_namespaces_and_one_writable_session() -> None:
    command = build_qemu_command(
        QemuWorkerConfig(
            Path("/opt/simulator/bin/qemu-system-xtensa"),
            Path("/opt/simulator/share/qemu"),
            sandbox_mode=WorkerSandboxMode.BUBBLEWRAP,
            sandbox_executable=Path("/usr/bin/bwrap"),
        ),
        CARDPUTER_ADV,
        Path("/run/esp32-s3/session/flash.bin"),
        Path("/run/esp32-s3/session/qmp.sock"),
        Path("/run/esp32-s3/session/gdb.sock"),
    )

    assert command[0] == "/usr/bin/bwrap"
    assert "--unshare-all" in command
    assert "--unshare-user" in command
    assert "--disable-userns" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command[command.index("--hostname") + 1] == "esp32-s3-worker"
    assert "--die-with-parent" in command
    assert "--clearenv" in command
    assert "--share-net" not in command
    writable_index = command.index("--bind")
    assert command[writable_index + 1 : writable_index + 3] == (
        "/run/esp32-s3/session",
        "/run/esp32-s3/session",
    )
    qemu_index = command.index("--") + 1
    assert command[qemu_index] == "/opt/simulator/bin/qemu-system-xtensa"
    assert command[command.index("-nic", qemu_index) + 1] == "none"


def test_worker_rejects_control_sockets_outside_its_session_directory() -> None:
    with pytest.raises(ValueError, match="share one session directory"):
        build_qemu_command(
            QemuWorkerConfig(
                Path("/opt/qemu"),
                Path("/opt/roms"),
                sandbox_mode=WorkerSandboxMode.BUBBLEWRAP,
            ),
            CARDPUTER_ADV,
            Path("/runtime/session/flash.bin"),
            Path("/runtime/other/qmp.sock"),
            None,
        )
