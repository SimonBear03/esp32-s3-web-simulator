# SPDX-License-Identifier: GPL-2.0-only

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import esp32_s3_simulator.sessions as sessions_module
from esp32_s3_simulator.boards import CARDPUTER_ADV, STICKS3, BoardProfile
from esp32_s3_simulator.firmware import ValidatedFirmware
from esp32_s3_simulator.framebuffer import RGBFrame, parse_framebuffer_packet
from esp32_s3_simulator.gdb import GdbRemoteError
from esp32_s3_simulator.recording import ReplayAction
from esp32_s3_simulator.sessions import (
    MAX_DEBUG_BREAKPOINTS,
    SessionManager,
    SessionRecord,
    SessionState,
    SessionTransitionError,
)
from esp32_s3_simulator.settings import Settings


def manager_with_session(
    tmp_path: Path, board: BoardProfile = CARDPUTER_ADV
) -> tuple[SessionManager, SessionRecord]:
    settings = Settings(
        runtime_root=tmp_path,
        qemu_executable=tmp_path / "qemu",
        rom_directory=tmp_path / "roms",
        native_workers_enabled=True,
        framebuffer_interval_ms=1,
    )
    manager = SessionManager(settings)
    now = datetime.now(UTC)
    runtime_directory = tmp_path / "session"
    runtime_directory.mkdir()
    session = SessionRecord(
        id="session-id",
        board=board,
        firmware=ValidatedFirmware(
            source_size_bytes=4096,
            flash_size_bytes=board.flash_size_bytes,
            source_sha256="a" * 64,
            flash_sha256="b" * 64,
            segment_count=1,
            flash_mode=0,
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=1),
        runtime_directory=runtime_directory,
        flash_path=runtime_directory / "flash.bin",
        qmp_socket_path=runtime_directory / "qmp.sock",
        gdb_socket_path=runtime_directory / "gdb.sock",
        state=SessionState.RUNNING,
    )
    manager._sessions[session.id] = session
    return manager, session


async def test_qmp_controls_enforce_and_update_session_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)
    commands: list[str] = []

    async def execute_qmp(
        _socket: Path, command: str, _arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        commands.append(command)
        return {}

    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)

    assert (await manager.pause(session.id)).state is SessionState.PAUSED
    with pytest.raises(SessionTransitionError, match="cannot pause"):
        await manager.pause(session.id)
    assert (await manager.reset(session.id)).state is SessionState.PAUSED
    assert (await manager.resume(session.id)).state is SessionState.RUNNING
    assert commands == ["stop", "system_reset", "cont"]


async def test_sticks3_runtime_inputs_reach_qmp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path, STICKS3)
    calls: list[tuple[str, dict[str, Any] | None]] = []

    async def execute_qmp(
        _socket: Path, command: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        calls.append((command, arguments))
        return {}

    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)

    await manager.send_button(session.id, "a", True)
    await manager.set_imu_sample(session.id, (1.0, 0.0, 0.0), (0.0, 0.0, 250.0))
    await manager.set_power_state(session.id, battery_mv=3700, vin_mv=0, charging=False)

    assert [call[0] for call in calls] == ["qom-set", "qom-set", "qom-set"]
    assert calls[0][1] == {
        "path": "/machine/peripheral/sticks3-buttons",
        "property": "button-a",
        "value": True,
    }
    assert calls[1][1] == {
        "path": "/machine/peripheral/sticks3-imu",
        "property": "sample",
        "value": "1000,0,0,0,0,250000",
    }
    assert calls[2][1] == {
        "path": "/machine/peripheral/sticks3-pmic",
        "property": "power-state",
        "value": "3700,0,0",
    }


async def test_recording_is_bounded_and_diagnostics_redact_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)
    manager._settings = Settings(
        runtime_root=tmp_path,
        qemu_executable=tmp_path / "qemu",
        rom_directory=tmp_path / "roms",
        native_workers_enabled=True,
        max_recording_events=3,
    )

    class FakeStdin:
        def write(self, _payload: bytes) -> None:
            pass

        async def drain(self) -> None:
            pass

    class FakeProcess:
        stdin = FakeStdin()

    async def execute_qmp(
        _socket: Path, _command: str, _arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)
    session.process = FakeProcess()  # type: ignore[assignment]
    secret = b"wifi-password=never-export-this"

    await manager.send_key(session.id, "a", True)
    await manager.send_key(session.id, "a", False)
    await manager.write_serial(session.id, secret)
    await manager.reset(session.id)

    events = manager.list_events(session.id, after=0, limit=100)
    diagnostics = manager.diagnostics(session.id)
    serialized = json.dumps(diagnostics)

    assert events["events_dropped"] == 1
    assert events["cursor_truncated"] is True
    assert len(events["events"]) == 3
    assert "never-export-this" not in serialized
    assert diagnostics["privacy"]["firmware_bytes_included"] is False  # type: ignore[index]
    assert diagnostics["privacy"]["serial_payloads_included"] is False  # type: ignore[index]
    assert session.replay_actions_dropped == 1


async def test_replay_restores_initial_flash_and_reapplies_recorded_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)
    session.initial_flash_image = b"original-flash-image"
    session.flash_path.write_bytes(b"mutated-nvs-state")
    session.replay_actions.append(ReplayAction(0, "key", ("enter", True)))
    qmp_calls: list[tuple[str, dict[str, Any] | None]] = []

    async def terminate_worker(_session: SessionRecord) -> None:
        _session.process = None
        _session.reader_task = None

    async def launch(_session: SessionRecord) -> None:
        _session.state = SessionState.RUNNING

    async def execute_qmp(
        _socket: Path, command: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        qmp_calls.append((command, arguments))
        return {}

    monkeypatch.setattr(manager, "_terminate_worker", terminate_worker)
    monkeypatch.setattr(manager, "_launch", launch)
    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)

    queued = await manager.start_replay(session.id, 1.0)
    task = session.replay_task
    assert task is not None
    await task

    assert queued["status"] == "queued"
    assert session.replay_status == "completed"
    assert session.generation == 2
    assert session.flash_path.read_bytes() == b"original-flash-image"
    assert [call[0] for call in qmp_calls] == ["input-send-event"]
    assert len(session.replay_actions) == 1
    assert manager.list_events(session.id)["events"][-1]["type"] == "replay.completed"  # type: ignore[index]


async def test_worker_peripheral_trace_is_parsed_and_capped(tmp_path: Path) -> None:
    manager, session = manager_with_session(tmp_path)
    manager._settings = Settings(
        runtime_root=tmp_path,
        qemu_executable=tmp_path / "qemu",
        rom_directory=tmp_path / "roms",
        native_workers_enabled=True,
        max_trace_events_per_generation=1,
    )
    stream = asyncio.StreamReader()
    stream.feed_data(b"esp32_gpio_input pin=11 level=0 interrupt=1\n")
    stream.feed_data(b"i2c_recv recv(addr:0x34) data:0x24\n")
    stream.feed_eof()

    await manager._read_worker_trace(session, stream)

    assert session.trace_events_recorded == 1
    assert session.trace_events_dropped == 1
    assert [event["type"] for event in manager.list_events(session.id)["events"]] == [
        "peripheral.gpio.input",
        "peripheral.trace.truncated",
    ]


async def test_noisy_worker_trace_is_sampled_without_hiding_later_inputs(
    tmp_path: Path,
) -> None:
    manager, session = manager_with_session(tmp_path)
    stream = asyncio.StreamReader()
    for _ in range(65):
        stream.feed_data(b"i2c_send send(addr:0x34) data:0x24\n")
    stream.feed_data(b"bmi270_sample accel_mg=1000,0,0 gyro_mdps=0,0,250000\n")
    stream.feed_eof()

    await manager._read_worker_trace(session, stream)

    event_types = [event["type"] for event in manager.list_events(session.id, limit=200)["events"]]
    assert event_types.count("peripheral.i2c.send") == 64
    assert event_types[-2:] == [
        "peripheral.trace.sampled",
        "peripheral.imu.sample",
    ]
    assert session.trace_events_recorded == 65
    assert session.trace_events_dropped == 1


async def test_global_trace_truncation_is_reported_after_source_sampling(
    tmp_path: Path,
) -> None:
    manager, session = manager_with_session(tmp_path)
    manager._settings = Settings(
        runtime_root=tmp_path,
        qemu_executable=tmp_path / "qemu",
        rom_directory=tmp_path / "roms",
        native_workers_enabled=True,
        max_trace_events_per_generation=65,
    )
    stream = asyncio.StreamReader()
    for _ in range(65):
        stream.feed_data(b"i2c_send send(addr:0x34) data:0x24\n")
    stream.feed_data(b"bmi270_sample accel_mg=1,2,3 gyro_mdps=4,5,6\n")
    stream.feed_data(b"sticks3_button button=a pressed=1\n")
    stream.feed_eof()

    await manager._read_worker_trace(session, stream)

    event_types = [event["type"] for event in manager.list_events(session.id, limit=200)["events"]]
    assert "peripheral.trace.sampled" in event_types
    assert "peripheral.imu.sample" in event_types
    assert event_types[-1] == "peripheral.trace.truncated"
    assert session.trace_events_recorded == 65
    assert session.trace_events_dropped == 2


async def test_stop_releases_private_firmware_uart_and_replay_data(
    tmp_path: Path,
) -> None:
    manager, session = manager_with_session(tmp_path)
    session.initial_flash_image = b"private-firmware"
    session.replay_actions.append(ReplayAction(1, "serial", b"private-uart"))
    session.serial_buffer.append(b"private-output")
    session.serial_output_bytes = len(b"private-output")

    await manager.stop(session.id)

    assert session.initial_flash_image == b""
    assert not session.replay_actions
    assert not session.serial_buffer
    diagnostics = json.dumps(manager.diagnostics(session.id))
    assert "private-firmware" not in diagnostics
    assert "private-uart" not in diagnostics
    assert "private-output" not in diagnostics
    assert session.serial_output_bytes == len(b"private-output")


async def test_capture_framebuffer_uses_private_qmp_file_and_removes_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)

    async def execute_qmp(
        _socket: Path, command: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert command == "screendump"
        assert arguments is not None
        Path(arguments["filename"]).write_bytes(b"P6\n1 1\n255\n" + bytes((1, 2, 3)))
        return {}

    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)

    frame = await manager.capture_framebuffer(session.id)

    assert frame.pixel(0, 0) == (1, 2, 3)
    assert not (session.runtime_directory / "framebuffer.ppm").exists()


async def test_framebuffer_subscription_suppresses_unchanged_frames(tmp_path: Path) -> None:
    manager, session = manager_with_session(tmp_path)
    frames = [
        RGBFrame(1, 1, bytes((255, 0, 0))),
        RGBFrame(1, 1, bytes((255, 0, 0))),
        RGBFrame(1, 1, bytes((0, 0, 255))),
    ]

    async def capture_framebuffer(_session_id: str) -> RGBFrame:
        return frames.pop(0)

    manager.capture_framebuffer = capture_framebuffer  # type: ignore[method-assign]
    updates = manager.subscribe_framebuffer(session.id)

    first_sequence, first = parse_framebuffer_packet(await anext(updates))
    second_sequence, second = parse_framebuffer_packet(await anext(updates))
    session.state = SessionState.STOPPED
    await updates.aclose()

    assert (first_sequence, first.pixel(0, 0)) == (0, (255, 0, 0))
    assert (second_sequence, second.pixel(0, 0)) == (1, (0, 0, 255))


async def test_serial_subscription_remains_attached_while_paused(tmp_path: Path) -> None:
    manager, session = manager_with_session(tmp_path)
    session.state = SessionState.PAUSED
    updates = manager.subscribe_serial(session.id)

    pending = asyncio.create_task(anext(updates))
    await asyncio.sleep(0)
    manager._publish(session, b"after-resume")

    assert await pending == b"after-resume"
    await updates.aclose()


async def test_debugger_requires_pause_and_enforces_breakpoint_quota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)

    class FakeGdbClient:
        async def read_registers(self) -> dict[str, int]:
            return {"pc": 0x42000000}

        async def read_memory(self, address: int, length: int) -> bytes:
            assert address == 0x42000000
            return bytes(range(length))

        async def add_breakpoint(self, _address: int) -> None:
            pass

        async def remove_breakpoint(self, _address: int) -> None:
            pass

        async def step(self) -> str:
            return "T05thread:1;"

    async def execute_qmp(
        _socket: Path, command: str, _arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert command == "query-status"
        return {"running": session.state is SessionState.RUNNING}

    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)
    session.gdb_client = FakeGdbClient()  # type: ignore[assignment]

    with pytest.raises(SessionTransitionError, match="require a paused session"):
        await manager.debug_registers(session.id)

    session.state = SessionState.PAUSED
    assert await manager.debug_registers(session.id) == {"pc": 0x42000000}
    assert await manager.debug_read_memory(session.id, 0x42000000, 4) == bytes(range(4))
    assert await manager.debug_step(session.id) == "T05thread:1;"

    for address in range(MAX_DEBUG_BREAKPOINTS):
        await manager.debug_set_breakpoint(session.id, address, True)
    with pytest.raises(GdbRemoteError, match="at most 32"):
        await manager.debug_set_breakpoint(session.id, MAX_DEBUG_BREAKPOINTS, True)

    await manager.debug_set_breakpoint(session.id, 0, False)
    await manager.debug_set_breakpoint(session.id, MAX_DEBUG_BREAKPOINTS, True)


async def test_debugger_resume_and_qmp_pause_keep_stop_state_synchronized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)
    session.state = SessionState.PAUSED
    stopped = asyncio.Event()

    class FakeGdbClient:
        async def continue_execution(self) -> str:
            await stopped.wait()
            return "T02thread:1;"

        async def close(self) -> None:
            pass

    async def execute_qmp(
        _socket: Path, command: str, _arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        assert command == "stop"
        stopped.set()
        return {}

    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)
    session.gdb_client = FakeGdbClient()  # type: ignore[assignment]

    assert (await manager.resume(session.id)).state is SessionState.RUNNING
    assert session.debug_run_task is not None
    assert (await manager.pause(session.id)).state is SessionState.PAUSED
    assert session.debug_run_task is None
    assert session.debug_stop_reason == "T02thread:1;"
