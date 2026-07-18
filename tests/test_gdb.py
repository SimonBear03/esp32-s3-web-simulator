# SPDX-License-Identifier: GPL-2.0-only

import asyncio
from pathlib import Path

import pytest

import esp32_s3_simulator.gdb as gdb_module
from esp32_s3_simulator.gdb import GdbRemoteClient, GdbRemoteError


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

    def is_closing(self) -> bool:
        return self.closed

    async def wait_closed(self) -> None:
        pass


def packet(payload: str) -> bytes:
    encoded = payload.encode()
    checksum = f"{sum(encoded) & 0xFF:02x}".encode()
    return b"$" + encoded + b"#" + checksum


def negotiated_reader(*responses: str) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(
        b"+" + packet("PacketSize=1000;qXfer:features:read+;QStartNoAckMode+") + b"+" + packet("OK")
    )
    for response in responses:
        reader.feed_data(packet(response))
    reader.feed_eof()
    return reader


def fallback_reader(*responses: str) -> asyncio.StreamReader:
    reader = asyncio.StreamReader()
    reader.feed_data(b"+" + packet("PacketSize=1000;QStartNoAckMode+") + b"+" + packet("OK"))
    for response in responses:
        reader.feed_data(packet(response))
    reader.feed_eof()
    return reader


async def connect_fake(
    monkeypatch: pytest.MonkeyPatch, *responses: str
) -> tuple[GdbRemoteClient, FakeWriter]:
    reader = negotiated_reader(*responses)
    writer = FakeWriter()

    async def open_connection(_path: Path) -> tuple[asyncio.StreamReader, FakeWriter]:
        return reader, writer

    monkeypatch.setattr(gdb_module.asyncio, "open_unix_connection", open_connection)
    return await GdbRemoteClient.connect(Path("/runtime/gdb.sock")), writer


async def connect_fallback(
    monkeypatch: pytest.MonkeyPatch, *responses: str
) -> tuple[GdbRemoteClient, FakeWriter]:
    reader = fallback_reader(*responses)
    writer = FakeWriter()

    async def open_connection(_path: Path) -> tuple[asyncio.StreamReader, FakeWriter]:
        return reader, writer

    monkeypatch.setattr(gdb_module.asyncio, "open_unix_connection", open_connection)
    return await GdbRemoteClient.connect(Path("/runtime/gdb.sock")), writer


async def test_gdb_discovers_and_reads_target_registers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_xml = (
        "<target><architecture>xtensa</architecture><feature name='core'>"
        "<reg name='pc' bitsize='32' regnum='0'/></feature></target>"
    )
    client, writer = await connect_fake(monkeypatch, f"l{target_xml}", "78563412")

    assert await client.read_registers() == {"pc": 0x12345678}
    assert any(write.startswith(b"$qXfer:features:read:target.xml") for write in writer.writes)
    assert any(write.startswith(b"$p0#") for write in writer.writes)
    await client.close()
    assert writer.closed


async def test_gdb_uses_esp32_s3_register_fallback_without_target_xml(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, writer = await connect_fallback(monkeypatch)

    registers = await client.register_definitions()

    assert registers[0].name == "pc"
    assert registers[64].name == "ar63"
    assert registers[-1].name == "gpio_out"
    assert len(registers) == 84
    assert not any(write.startswith(b"$qXfer:features:read:") for write in writer.writes)


async def test_gdb_reads_memory_and_controls_breakpoints_and_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _writer = await connect_fake(monkeypatch, "01020304", "OK", "OK", "T05thread:1;")

    assert await client.read_memory(0x42000000, 4) == b"\x01\x02\x03\x04"
    await client.add_breakpoint(0x42000000)
    await client.remove_breakpoint(0x42000000)
    assert await client.step() == "T05thread:1;"


async def test_gdb_rejects_bad_memory_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _writer = await connect_fake(monkeypatch)

    with pytest.raises(GdbRemoteError, match="between 1 and 4096"):
        await client.read_memory(0, 4097)


async def test_gdb_wraps_a_closed_private_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _writer = await connect_fake(monkeypatch)

    with pytest.raises(GdbRemoteError, match="closed the private GDB connection"):
        await client.read_memory(0x42000000, 4)
