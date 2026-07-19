# SPDX-License-Identifier: GPL-2.0-only

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from esp32_s3_simulator import qmp


class FakeWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, payload: bytes) -> None:
        self.writes.append(payload)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


def qmp_reader(*messages: dict[str, Any]) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    for message in messages:
        reader.feed_data(json.dumps(message).encode() + b"\n")
    reader.feed_eof()
    return reader


async def test_execute_qmp_negotiates_capabilities_and_sends_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = qmp_reader(
        {"QMP": {"version": {"qemu": {"major": 9}}}},
        {"return": {}, "id": "capabilities"},
        {"event": "RESET"},
        {"return": {"accepted": True}, "id": "command"},
    )
    writer = FakeWriter()

    async def open_connection(_path: Path) -> tuple[asyncio.StreamReader, FakeWriter]:
        return reader, writer

    monkeypatch.setattr(qmp.asyncio, "open_unix_connection", open_connection)
    result = await qmp.execute_qmp(
        Path("/runtime/qmp.sock"),
        "input-send-event",
        {"events": []},
    )

    assert result == {"accepted": True}
    assert [json.loads(payload) for payload in writer.writes] == [
        {"execute": "qmp_capabilities", "id": "capabilities"},
        {
            "execute": "input-send-event",
            "id": "command",
            "arguments": {"events": []},
        },
    ]
    assert writer.closed


async def test_execute_qmp_surfaces_command_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = qmp_reader(
        {"QMP": {"version": {"qemu": {"major": 9}}}},
        {"return": {}, "id": "capabilities"},
        {"error": {"class": "GenericError", "desc": "bad key"}, "id": "command"},
    )
    writer = FakeWriter()

    async def open_connection(_path: Path) -> tuple[asyncio.StreamReader, FakeWriter]:
        return reader, writer

    monkeypatch.setattr(qmp.asyncio, "open_unix_connection", open_connection)
    with pytest.raises(qmp.QmpCommandError, match="bad key"):
        await qmp.execute_qmp(Path("/runtime/qmp.sock"), "input-send-event")


async def test_execute_qmp_preserves_scalar_qom_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = qmp_reader(
        {"QMP": {"version": {"qemu": {"major": 9}}}},
        {"return": {}, "id": "capabilities"},
        {"return": True, "id": "command"},
    )
    writer = FakeWriter()

    async def open_connection(_path: Path) -> tuple[asyncio.StreamReader, FakeWriter]:
        return reader, writer

    monkeypatch.setattr(qmp.asyncio, "open_unix_connection", open_connection)

    assert await qmp.execute_qmp(Path("/runtime/qmp.sock"), "qom-get") is True


async def test_execute_qmp_ignores_peer_reset_during_socket_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = qmp_reader(
        {"QMP": {"version": {"qemu": {"major": 9}}}},
        {"return": {}, "id": "capabilities"},
        {"return": {"accepted": True}, "id": "command"},
    )

    class ResettingWriter(FakeWriter):
        async def wait_closed(self) -> None:
            raise ConnectionResetError("QEMU closed first")

    writer = ResettingWriter()

    async def open_connection(_path: Path) -> tuple[asyncio.StreamReader, FakeWriter]:
        return reader, writer

    monkeypatch.setattr(qmp.asyncio, "open_unix_connection", open_connection)

    assert await qmp.execute_qmp(Path("/runtime/qmp.sock"), "query-status") == {
        "accepted": True
    }
    assert writer.closed
