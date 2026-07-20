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
from esp32_s3_simulator.qmp import QmpUnavailableError
from esp32_s3_simulator.recording import ReplayAction
from esp32_s3_simulator.sessions import (
    MAX_DEBUG_BREAKPOINTS,
    SessionManager,
    SessionRecord,
    SessionState,
    SessionTransitionError,
    WorkerUnavailableError,
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


async def test_manager_rejects_runtime_root_that_cannot_fit_private_sockets(
    tmp_path: Path,
) -> None:
    settings = Settings(
        runtime_root=tmp_path / ("runtime-" + "x" * 80),
        qemu_executable=tmp_path / "qemu",
        rom_directory=tmp_path / "roms",
        native_workers_enabled=True,
    )

    with pytest.raises(WorkerUnavailableError, match="too long"):
        await SessionManager(settings).start()


async def test_power_cycle_stops_and_relaunches_worker_without_restoring_flash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)
    process = FakeWorkerProcess()
    session.process = process
    session.flash_path.write_bytes(b"mutated-nvs")
    session.virtual_power_state = (3750, 0, False)
    session.qmp_socket_path.touch()
    session.gdb_socket_path.touch()
    qmp_calls: list[tuple[str, dict[str, Any] | None]] = []

    powered_off = await manager.power_off(session.id)

    assert process.terminated is True
    assert powered_off.state is SessionState.POWERED_OFF
    assert powered_off.exit_code is None
    assert powered_off.flash_path.read_bytes() == b"mutated-nvs"
    assert powered_off.replay_actions[-1].type == "power_off"

    async def launch(next_session: SessionRecord) -> None:
        assert next_session.state is SessionState.STARTING
        assert next_session.flash_path.read_bytes() == b"mutated-nvs"
        assert not next_session.qmp_socket_path.exists()
        assert not next_session.gdb_socket_path.exists()
        next_session.state = SessionState.RUNNING

    async def execute_qmp(
        _socket: Path, command: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        qmp_calls.append((command, arguments))
        return {}

    monkeypatch.setattr(manager, "_launch", launch)
    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)
    powered_on = await manager.power_on(session.id)

    assert powered_on.state is SessionState.RUNNING
    assert powered_on.generation == 1
    assert [command for command, _arguments in qmp_calls] == ["qom-set"]
    assert [action.type for action in powered_on.replay_actions] == [
        "power_off",
        "power_on",
    ]

    with pytest.raises(SessionTransitionError, match="cannot power on"):
        await manager.power_on(session.id)


async def test_failed_power_on_destroys_private_session_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)
    session.state = SessionState.POWERED_OFF
    session.initial_flash_image = b"private-original"
    session.flash_path.write_bytes(b"private-mutated-nvs")
    session.replay_actions.append(ReplayAction(1, "serial", b"private-uart"))
    session.virtual_power_state = (3750, 0, False)

    async def launch(_session: SessionRecord) -> None:
        raise WorkerUnavailableError("cold boot failed")

    monkeypatch.setattr(manager, "_launch", launch)

    with pytest.raises(WorkerUnavailableError, match="cold boot failed"):
        await manager.power_on(session.id)

    assert session.state is SessionState.FAILED
    assert session.initial_flash_image == b""
    assert not session.replay_actions
    assert session.virtual_power_state is None
    assert not session.runtime_directory.exists()


async def test_stop_cannot_be_overtaken_by_inflight_power_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)
    session.state = SessionState.POWERED_OFF
    session.initial_flash_image = b"private-original"
    session.flash_path.write_bytes(b"private-mutated-nvs")
    launch_started = asyncio.Event()
    finish_launch = asyncio.Event()

    async def launch(_session: SessionRecord) -> None:
        launch_started.set()
        await finish_launch.wait()
        _session.state = SessionState.RUNNING

    monkeypatch.setattr(manager, "_launch", launch)
    power_on_task = asyncio.create_task(manager.power_on(session.id))
    await launch_started.wait()
    stop_task = asyncio.create_task(manager.stop(session.id))
    await asyncio.sleep(0)

    assert not stop_task.done()
    finish_launch.set()
    await power_on_task
    stopped = await stop_task

    assert stopped.state is SessionState.STOPPED
    assert stopped.initial_flash_image == b""
    assert not stopped.replay_actions
    assert not stopped.runtime_directory.exists()


class FakeWorkerProcess:
    def __init__(self) -> None:
        self.stdin = None
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self._returncode: int | None = None
        self._waiter = asyncio.Event()
        self.terminated = False

    @property
    def returncode(self) -> int | None:
        return self._returncode

    async def wait(self) -> int:
        await self._waiter.wait()
        assert self._returncode is not None
        return self._returncode

    def terminate(self) -> None:
        self.terminated = True
        self._finish(-15)

    def kill(self) -> None:
        self._finish(-9)

    def _finish(self, returncode: int) -> None:
        if self._returncode is not None:
            return
        self._returncode = returncode
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self._waiter.set()


def prepare_launch_manager(
    manager: SessionManager,
    tmp_path: Path,
    *,
    startup_timeout_seconds: float = 4.25,
) -> tuple[SessionManager, SessionRecord]:
    qemu = tmp_path / "qemu"
    qemu.touch(mode=0o700)
    (tmp_path / "roms").mkdir()
    manager._settings = Settings(
        runtime_root=tmp_path,
        qemu_executable=qemu,
        rom_directory=tmp_path / "roms",
        native_workers_enabled=True,
        worker_startup_timeout_seconds=startup_timeout_seconds,
    )
    return manager, manager.get("session-id")


async def test_launch_waits_for_running_qmp_before_exposing_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, _session = manager_with_session(tmp_path)
    manager, session = prepare_launch_manager(manager, tmp_path)
    session.state = SessionState.STARTING
    process = FakeWorkerProcess()
    calls: list[tuple[str, float]] = []

    async def launch_local_worker(*_args: object) -> FakeWorkerProcess:
        return process

    async def execute_qmp(
        _socket: Path,
        command: str,
        _arguments: dict[str, Any] | None = None,
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        assert session.state is SessionState.STARTING
        calls.append((command, timeout_seconds))
        if len(calls) == 1:
            return {"running": False, "status": "prelaunch"}
        return {"running": True, "status": "running"}

    monkeypatch.setattr(manager, "_launch_local_worker", launch_local_worker)
    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)

    await manager._launch(session)

    assert [command for command, _timeout in calls] == ["query-status", "query-status"]
    assert all(0 < timeout <= 1 for _command, timeout in calls)
    assert session.state is SessionState.RUNNING
    assert session.process is process
    await manager._terminate_worker(session)


async def test_launch_terminates_worker_when_qmp_never_becomes_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager, _session = manager_with_session(tmp_path)
    manager, session = prepare_launch_manager(
        manager,
        tmp_path,
        startup_timeout_seconds=0.02,
    )
    session.state = SessionState.STARTING
    process = FakeWorkerProcess()

    async def launch_local_worker(*_args: object) -> FakeWorkerProcess:
        return process

    async def execute_qmp(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise QmpUnavailableError("private socket detail")

    monkeypatch.setattr(manager, "_launch_local_worker", launch_local_worker)
    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)

    with pytest.raises(
        WorkerUnavailableError,
        match="failed its startup readiness check",
    ) as caught:
        await manager._launch(session)

    assert "private socket detail" not in str(caught.value)
    assert "cause=WorkerUnavailableError" in caplog.text
    assert "private socket detail" not in caplog.text
    assert process.terminated is True
    assert session.process is None


async def test_worker_exit_during_startup_marks_session_failed(tmp_path: Path) -> None:
    manager, session = manager_with_session(tmp_path)
    session.state = SessionState.STARTING
    session.initial_flash_image = b"private-firmware"
    process = FakeWorkerProcess()
    session.process = process
    process._finish(1)

    await manager._read_serial(session, process)

    assert session.state is SessionState.FAILED
    assert session.exit_code == 1
    assert session.initial_flash_image == b""
    assert not session.runtime_directory.exists()


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
    assert session.accept_live_input is False
    with pytest.raises(RuntimeError, match="replay is running"):
        await manager.power_off(session.id)
    await task

    assert queued["status"] == "queued"
    assert session.replay_status == "completed"
    assert session.generation == 2
    assert session.flash_path.read_bytes() == b"original-flash-image"
    assert [call[0] for call in qmp_calls] == ["input-send-event"]
    assert len(session.replay_actions) == 1
    assert manager.list_events(session.id)["events"][-1]["type"] == "replay.completed"  # type: ignore[index]


async def test_replay_reproduces_a_cold_power_cycle_and_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)
    session.initial_flash_image = b"original-flash-image"
    session.flash_path.write_bytes(b"mutated-nvs-state")
    session.replay_actions.extend(
        (
            ReplayAction(0, "power", (3710, 0, False)),
            ReplayAction(1, "power_off", None),
            ReplayAction(2, "power_on", None),
        )
    )
    launch_count = 0
    terminate_count = 0
    qmp_calls: list[str] = []

    async def terminate_worker(_session: SessionRecord) -> None:
        nonlocal terminate_count
        terminate_count += 1
        _session.process = None
        _session.reader_task = None

    async def launch(_session: SessionRecord) -> None:
        nonlocal launch_count
        launch_count += 1
        _session.state = SessionState.RUNNING

    async def execute_qmp(
        _socket: Path, command: str, _arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        qmp_calls.append(command)
        return {}

    monkeypatch.setattr(manager, "_terminate_worker", terminate_worker)
    monkeypatch.setattr(manager, "_launch", launch)
    monkeypatch.setattr(sessions_module, "execute_qmp", execute_qmp)

    await manager.start_replay(session.id, 1.0)
    task = session.replay_task
    assert task is not None
    await task

    assert session.replay_status == "completed"
    assert session.state is SessionState.RUNNING
    assert session.generation == 2
    assert session.virtual_power_state == (3710, 0, False)
    assert [action.type for action in session.replay_actions] == [
        "power",
        "power_off",
        "power_on",
    ]
    assert launch_count == 2
    assert terminate_count == 2
    assert qmp_calls == ["qom-set", "qom-set"]


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


async def test_noisy_trace_reader_yields_to_worker_control_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, session = manager_with_session(tmp_path)
    stream = asyncio.StreamReader()
    for _ in range(sessions_module.TRACE_READER_YIELD_LINES * 2):
        stream.feed_data(b"unrecognized_worker_noise\n")
    stream.feed_eof()
    original_sleep = asyncio.sleep
    cooperative_yields = 0

    async def sleep(delay: float) -> None:
        nonlocal cooperative_yields
        assert delay == 0
        cooperative_yields += 1
        await original_sleep(0)

    monkeypatch.setattr(sessions_module.asyncio, "sleep", sleep)

    await manager._read_worker_trace(session, stream)

    assert cooperative_yields == 2


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
