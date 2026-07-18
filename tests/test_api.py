# SPDX-License-Identifier: GPL-2.0-only

from pathlib import Path

from httpx import ASGITransport, AsyncClient

from esp32_s3_simulator.api import KeyInputMessage, SessionControlMessage, create_app
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
        }

        boards = (await client.get("/v1/boards")).json()
        assert [board["id"] for board in boards] == ["cardputer-adv", "sticks3"]
        assert boards[0]["capabilities"][3]["fidelity"] == "emulated"
        assert boards[0]["capabilities"][4]["fidelity"] == "emulated"


def test_input_message_contract_rejects_untyped_payloads() -> None:
    assert KeyInputMessage.model_validate(
        {"type": "key", "key": "a", "pressed": True, "sequence": 12}
    ).sequence == 12
    assert SessionControlMessage.model_validate({"action": "pause"}).action == "pause"


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
