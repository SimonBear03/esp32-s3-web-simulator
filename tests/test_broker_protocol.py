# SPDX-License-Identifier: GPL-2.0-only

import asyncio
import json
import struct
from pathlib import Path

import pytest

from esp32_s3_simulator.broker_protocol import (
    MAX_CONTROL_PAYLOAD,
    BrokerProtocolError,
    ErrorMessage,
    ExitMessage,
    FrameKind,
    FrameWriter,
    StartRequest,
    connect_broker_worker,
    probe_broker,
    read_frame,
)

SESSION_ID = "a" * 32


def test_start_request_is_strict_and_round_trips() -> None:
    request = StartRequest(session_id=SESSION_ID, board_id="cardputer-adv")

    assert StartRequest.from_payload(request.to_payload()) == request

    with pytest.raises(BrokerProtocolError, match="unexpected"):
        StartRequest.from_payload(
            json.dumps(
                {
                    "protocol": 1,
                    "session_id": SESSION_ID,
                    "board_id": "cardputer-adv",
                    "image": "attacker-controlled",
                }
            ).encode()
        )
    with pytest.raises(BrokerProtocolError, match="32 lowercase"):
        StartRequest(session_id="../escape", board_id="cardputer-adv")
    with pytest.raises(BrokerProtocolError, match="owned simulator profile"):
        StartRequest(session_id=SESSION_ID, board_id="unowned-board")


async def test_frame_reader_rejects_unknown_and_oversized_frames() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(struct.pack("!BI", 255, 0))
    reader.feed_eof()
    with pytest.raises(BrokerProtocolError, match="type is unknown"):
        await read_frame(reader)

    reader = asyncio.StreamReader()
    reader.feed_data(struct.pack("!BI", FrameKind.START, MAX_CONTROL_PAYLOAD + 1))
    reader.feed_eof()
    with pytest.raises(BrokerProtocolError, match="exceeds"):
        await read_frame(reader, max_payload=MAX_CONTROL_PAYLOAD)


async def test_broker_process_relays_streams_and_control(tmp_path: Path) -> None:
    socket_path = tmp_path / "broker.sock"
    request_seen: asyncio.Future[StartRequest] = asyncio.get_running_loop().create_future()
    stdin_seen: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
    terminate_seen = asyncio.Event()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        frames = FrameWriter(writer)
        start = await read_frame(reader, max_payload=MAX_CONTROL_PAYLOAD)
        assert start.kind is FrameKind.START
        request_seen.set_result(StartRequest.from_payload(start.payload))
        await frames.send(FrameKind.STARTED)
        stdin = await read_frame(reader)
        assert stdin.kind is FrameKind.STDIN
        stdin_seen.set_result(stdin.payload)
        await frames.send(FrameKind.STDOUT, b"serial-output")
        await frames.send(FrameKind.STDERR, b"trace-output\n")
        control = await read_frame(reader, max_payload=0)
        assert control.kind is FrameKind.TERMINATE
        terminate_seen.set()
        await frames.send(FrameKind.EXIT, ExitMessage(0).to_payload())
        await frames.close()

    server = await asyncio.start_unix_server(handle, path=socket_path)
    async with server:
        process = await connect_broker_worker(
            socket_path,
            StartRequest(session_id=SESSION_ID, board_id="cardputer-adv"),
        )
        assert process.stdin is not None
        process.stdin.write(b"serial-input")
        await process.stdin.drain()

        assert await asyncio.wait_for(process.stdout.readexactly(13), 1) == b"serial-output"
        assert await asyncio.wait_for(process.stderr.readline(), 1) == b"trace-output\n"
        process.terminate()
        assert await asyncio.wait_for(process.wait(), 1) == 0
        await asyncio.wait_for(terminate_seen.wait(), 1)

    assert await request_seen == StartRequest(session_id=SESSION_ID, board_id="cardputer-adv")
    assert await stdin_seen == b"serial-input"


async def test_broker_launch_error_is_redacted(tmp_path: Path) -> None:
    socket_path = tmp_path / "broker.sock"

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        frames = FrameWriter(writer)
        start = await read_frame(reader)
        assert start.kind is FrameKind.START
        await frames.send(
            FrameKind.ERROR,
            ErrorMessage("capacity", "All isolated workers are busy").to_payload(),
        )
        await frames.close()

    server = await asyncio.start_unix_server(handle, path=socket_path)
    async with server:
        with pytest.raises(RuntimeError, match="capacity") as caught:
            await connect_broker_worker(
                socket_path,
                StartRequest(session_id=SESSION_ID, board_id="sticks3"),
            )

    assert "All isolated workers" not in str(caught.value)


async def test_broker_probe_requires_exact_pong(tmp_path: Path) -> None:
    socket_path = tmp_path / "broker.sock"

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        frames = FrameWriter(writer)
        ping = await read_frame(reader, max_payload=0)
        assert ping.kind is FrameKind.PING
        await frames.send(FrameKind.PONG)
        await frames.close()

    server = await asyncio.start_unix_server(handle, path=socket_path)
    async with server:
        assert await probe_broker(socket_path)

    assert not await probe_broker(socket_path)
