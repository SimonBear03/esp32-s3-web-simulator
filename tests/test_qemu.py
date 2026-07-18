# SPDX-License-Identifier: GPL-2.0-only

from pathlib import Path

from esp32_s3_simulator.boards import CARDPUTER_ADV, STICKS3
from esp32_s3_simulator.qemu import QemuWorkerConfig, build_qemu_command


def command_for(board_id: str) -> tuple[str, ...]:
    board = CARDPUTER_ADV if board_id == CARDPUTER_ADV.id else STICKS3
    return build_qemu_command(
        QemuWorkerConfig(Path("/opt/qemu"), Path("/opt/roms")),
        board,
        Path("/runtime/flash.bin"),
        Path("/runtime/qmp.sock"),
    )


def test_worker_command_disables_network_and_exposes_qmp_and_serial() -> None:
    command = command_for("cardputer-adv")

    assert command[:5] == ("/opt/qemu", "-L", "/opt/roms", "-M", "esp32s3")
    assert command[command.index("-nic") + 1] == "none"
    assert command[command.index("-serial") + 1] == "stdio"
    assert command[command.index("-monitor") + 1] == "none"
    assert command[command.index("-qmp") + 1].startswith("unix:/runtime/qmp.sock")
    assert "-m" not in command


def test_sticks3_worker_enables_eight_mebibytes_of_psram() -> None:
    command = command_for("sticks3")
    assert command[command.index("-m") + 1] == "8M"


def test_qmp_can_be_disabled_for_restricted_test_sandboxes() -> None:
    command = build_qemu_command(
        QemuWorkerConfig(Path("/opt/qemu"), Path("/opt/roms")),
        CARDPUTER_ADV,
        Path("/runtime/flash.bin"),
        None,
    )
    assert "-qmp" not in command
