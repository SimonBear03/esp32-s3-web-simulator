# SPDX-License-Identifier: GPL-2.0-only

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from esp32_s3_simulator.api import (
    INPUT_MESSAGE_ADAPTER,
    ButtonInputMessage,
    DebugBreakpointMessage,
    DebugMemoryReadMessage,
    ImuInputMessage,
    KeyInputMessage,
    PowerInputMessage,
    SessionControlMessage,
    SessionReplayMessage,
    create_app,
)
from esp32_s3_simulator.sessions import SessionState, WorkerUnavailableError
from esp32_s3_simulator.settings import Settings


def disabled_settings(tmp_path: Path) -> Settings:
    return Settings(
        runtime_root=tmp_path / "runtime",
        qemu_executable=tmp_path / "missing-qemu",
        rom_directory=tmp_path / "missing-roms",
        native_workers_enabled=False,
    )


async def test_health_and_board_contract(tmp_path: Path) -> None:
    app = create_app(disabled_settings(tmp_path))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app), base_url="http://simulator.test"
        ) as client,
    ):
        assert (await client.get("/health/live")).json()["status"] == "ok"
        assert (await client.get("/health/ready")).json() == {
            "status": "degraded",
            "native_worker": False,
            "worker_sandbox": "direct",
        }

        boards = (await client.get("/v1/boards")).json()
        assert [board["id"] for board in boards] == ["cardputer-adv", "sticks3"]
        assert boards[0]["capabilities"][3]["fidelity"] == "emulated"
        assert boards[0]["capabilities"][4]["fidelity"] == "emulated"


def test_input_message_contract_rejects_untyped_payloads() -> None:
    assert KeyInputMessage.model_validate(
        {"type": "key", "key": "a", "pressed": True, "sequence": 12}
    ).sequence == 12
    assert isinstance(
        INPUT_MESSAGE_ADAPTER.validate_python(
            {"type": "button", "button": "a", "pressed": True}
        ),
        ButtonInputMessage,
    )
    assert isinstance(
        INPUT_MESSAGE_ADAPTER.validate_python(
            {
                "type": "imu",
                "acceleration_g": {"x": 0, "y": 0, "z": 1},
                "angular_velocity_dps": {"x": 0, "y": 0, "z": 0},
            }
        ),
        ImuInputMessage,
    )
    assert isinstance(
        INPUT_MESSAGE_ADAPTER.validate_python(
            {
                "type": "power",
                "battery_mv": 3900,
                "vin_mv": 5000,
                "charging": True,
            }
        ),
        PowerInputMessage,
    )
    assert SessionControlMessage.model_validate({"action": "pause"}).action == "pause"
    assert SessionControlMessage.model_validate({"action": "power-off"}).action == "power-off"
    assert SessionControlMessage.model_validate({"action": "power-on"}).action == "power-on"
    assert SessionReplayMessage.model_validate({}).speed == 1.0
    assert (
        DebugMemoryReadMessage.model_validate({"address": 0x42000000, "length": 4096}).length
        == 4096
    )
    assert DebugBreakpointMessage.model_validate({"address": 0x42000000, "enabled": True}).enabled


async def test_session_creation_fails_closed_without_worker(tmp_path: Path) -> None:
    firmware = bytes((0xE9, 1, 0, 0)) + bytes(4092)
    app = create_app(disabled_settings(tmp_path))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app), base_url="http://simulator.test"
        ) as client,
    ):
        response = await client.post(
            "/v1/sessions",
            data={"board_id": "cardputer-adv"},
            files={"firmware": ("firmware.bin", firmware, "application/octet-stream")},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "native QEMU workers are not configured and enabled"


async def test_session_control_contract_rejects_invalid_or_missing_sessions(
    tmp_path: Path,
) -> None:
    app = create_app(disabled_settings(tmp_path))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app), base_url="http://simulator.test"
        ) as client,
    ):
        invalid = await client.post(
            "/v1/sessions/missing/control", json={"action": "explode"}
        )
        missing = await client.post(
            "/v1/sessions/missing/control", json={"action": "pause"}
        )

    assert invalid.status_code == 422
    assert missing.status_code == 404


async def test_failed_power_on_is_reported_as_worker_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    app = create_app(disabled_settings(tmp_path))
    manager = app.state.session_manager

    async def power_on(session_id: str) -> None:
        assert session_id == "session-id"
        raise WorkerUnavailableError("cold boot failed")

    monkeypatch.setattr(manager, "power_on", power_on)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app), base_url="http://simulator.test"
        ) as client,
    ):
        response = await client.post(
            "/v1/sessions/session-id/control", json={"action": "power-on"}
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "cold boot failed"


async def test_recording_diagnostics_and_replay_api_contract(
    tmp_path: Path, monkeypatch
) -> None:
    app = create_app(disabled_settings(tmp_path))
    manager = app.state.session_manager

    def list_events(session_id: str, *, after: int, limit: int) -> dict[str, object]:
        assert (session_id, after, limit) == ("session-id", 7, 12)
        return {"events": [], "next_after": 7}

    def diagnostics(session_id: str) -> dict[str, object]:
        assert session_id == "session-id"
        return {
            "schema": "esp32-s3-simulator-diagnostics/v1",
            "privacy": {"firmware_bytes_included": False},
        }

    def replay_status(session_id: str) -> dict[str, object]:
        assert session_id == "session-id"
        return {"status": "completed"}

    async def start_replay(session_id: str, speed: float) -> dict[str, object]:
        assert (session_id, speed) == ("session-id", 2.0)
        return {"status": "queued", "speed": speed}

    monkeypatch.setattr(manager, "list_events", list_events)
    monkeypatch.setattr(manager, "diagnostics", diagnostics)
    monkeypatch.setattr(manager, "replay_status", replay_status)
    monkeypatch.setattr(manager, "start_replay", start_replay)

    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app=app), base_url="http://simulator.test"
        ) as client,
    ):
        events = await client.get("/v1/sessions/session-id/events?after=7&limit=12")
        bundle = await client.get("/v1/sessions/session-id/diagnostics")
        status = await client.get("/v1/sessions/session-id/replay")
        replay = await client.post(
            "/v1/sessions/session-id/replay", json={"speed": 2}
        )
        invalid = await client.post(
            "/v1/sessions/session-id/replay", json={"speed": 5}
        )

    assert events.json() == {"events": [], "next_after": 7}
    assert bundle.headers["content-disposition"].endswith('session-id.json"')
    assert bundle.headers["cache-control"] == "no-store"
    assert status.json() == {"status": "completed"}
    assert replay.status_code == 202
    assert replay.json() == {"status": "queued", "speed": 2.0}
    assert invalid.status_code == 422


async def test_debug_api_is_typed_bounded_and_does_not_expose_raw_gdb(
    tmp_path: Path, monkeypatch
) -> None:
    app = create_app(disabled_settings(tmp_path))
    manager = app.state.session_manager

    class FakeSession:
        state = SessionState.PAUSED
        debug_stop_reason = "T05thread:1;"

    async def refresh_state(session_id: str) -> FakeSession:
        assert session_id == "session-id"
        return FakeSession()

    async def debug_registers(session_id: str) -> dict[str, int]:
        assert session_id == "session-id"
        return {"pc": 0x42000000}

    async def debug_read_memory(session_id: str, address: int, length: int) -> bytes:
        assert (session_id, address, length) == ("session-id", 0x42000000, 4)
        return b"\x01\x02\x03\x04"

    breakpoint_calls: list[tuple[str, int, bool]] = []

    async def debug_set_breakpoint(session_id: str, address: int, enabled: bool) -> None:
        breakpoint_calls.append((session_id, address, enabled))

    async def debug_step(session_id: str) -> str:
        assert session_id == "session-id"
        return "T05thread:1;"

    monkeypatch.setattr(manager, "refresh_state", refresh_state)
    monkeypatch.setattr(manager, "debug_registers", debug_registers)
    monkeypatch.setattr(manager, "debug_read_memory", debug_read_memory)
    monkeypatch.setattr(manager, "debug_set_breakpoint", debug_set_breakpoint)
    monkeypatch.setattr(manager, "debug_step", debug_step)

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://simulator.test") as client,
    ):
        status = (await client.get("/v1/sessions/session-id/debug/status")).json()
        registers = (await client.get("/v1/sessions/session-id/debug/registers")).json()
        memory = (
            await client.post(
                "/v1/sessions/session-id/debug/memory",
                json={"address": 0x42000000, "length": 4},
            )
        ).json()
        breakpoint = (
            await client.post(
                "/v1/sessions/session-id/debug/breakpoint",
                json={"address": 0x42000000, "enabled": True},
            )
        ).json()
        step = (await client.post("/v1/sessions/session-id/debug/step")).json()
        oversized = await client.post(
            "/v1/sessions/session-id/debug/memory",
            json={"address": 0, "length": 4097},
        )

    assert status["state"] == "paused"
    assert status["capabilities"]["memory_read_max_bytes"] == 4096
    assert status["capabilities"]["hardware_breakpoints_max"] == 32
    assert status["capabilities"]["raw_gdb"] is False
    assert registers == {"registers": {"pc": 0x42000000}}
    assert memory == {"address": 0x42000000, "length": 4, "data_hex": "01020304"}
    assert breakpoint == {"address": 0x42000000, "enabled": True}
    assert breakpoint_calls == [("session-id", 0x42000000, True)]
    assert step == {"stop_reason": "T05thread:1;"}
    assert oversized.status_code == 422
