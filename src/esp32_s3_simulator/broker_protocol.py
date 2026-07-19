# SPDX-License-Identifier: GPL-2.0-only

import asyncio
import json
import re
import struct
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

from .boards import BOARD_PROFILES

PROTOCOL_VERSION = 1
MAX_FRAME_PAYLOAD = 256 * 1024
MAX_CONTROL_PAYLOAD = 4096
MAX_STREAM_CHUNK = 64 * 1024
MAX_BUFFERED_STDIN = 256 * 1024
_FRAME_HEADER = struct.Struct("!BI")
_SESSION_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_ERROR_CODE_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


class BrokerProtocolError(RuntimeError):
    pass


class BrokerUnavailableError(RuntimeError):
    pass


class FrameKind(IntEnum):
    PING = 1
    PONG = 2
    START = 3
    STARTED = 4
    STDIN = 5
    TERMINATE = 6
    KILL = 7
    STDOUT = 8
    STDERR = 9
    EXIT = 10
    ERROR = 11


@dataclass(frozen=True, slots=True)
class BrokerFrame:
    kind: FrameKind
    payload: bytes = b""


def _json_object(payload: bytes, *, label: str) -> dict[str, Any]:
    if len(payload) > MAX_CONTROL_PAYLOAD:
        raise BrokerProtocolError(f"{label} payload is too large")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BrokerProtocolError(f"{label} payload is not valid JSON") from error
    if not isinstance(value, dict):
        raise BrokerProtocolError(f"{label} payload must be a JSON object")
    return value


def _json_payload(value: dict[str, object]) -> bytes:
    payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    if len(payload) > MAX_CONTROL_PAYLOAD:
        raise BrokerProtocolError("control payload is too large")
    return payload


@dataclass(frozen=True, slots=True)
class StartRequest:
    session_id: str
    board_id: str

    def __post_init__(self) -> None:
        if not _SESSION_ID_PATTERN.fullmatch(self.session_id):
            raise BrokerProtocolError("session ID must be 32 lowercase hexadecimal characters")
        if self.board_id not in BOARD_PROFILES:
            raise BrokerProtocolError("board ID is not an owned simulator profile")

    def to_payload(self) -> bytes:
        return _json_payload(
            {
                "protocol": PROTOCOL_VERSION,
                "session_id": self.session_id,
                "board_id": self.board_id,
            }
        )

    @classmethod
    def from_payload(cls, payload: bytes) -> "StartRequest":
        value = _json_object(payload, label="start")
        if set(value) != {"protocol", "session_id", "board_id"}:
            raise BrokerProtocolError("start payload contains missing or unexpected fields")
        protocol = value["protocol"]
        if isinstance(protocol, bool) or protocol != PROTOCOL_VERSION:
            raise BrokerProtocolError("broker protocol version is not supported")
        session_id = value["session_id"]
        board_id = value["board_id"]
        if not isinstance(session_id, str) or not isinstance(board_id, str):
            raise BrokerProtocolError("start identifiers must be strings")
        return cls(session_id=session_id, board_id=board_id)


@dataclass(frozen=True, slots=True)
class ExitMessage:
    returncode: int

    def __post_init__(self) -> None:
        if isinstance(self.returncode, bool) or not -255 <= self.returncode <= 255:
            raise BrokerProtocolError("worker return code is out of range")

    def to_payload(self) -> bytes:
        return _json_payload({"returncode": self.returncode})

    @classmethod
    def from_payload(cls, payload: bytes) -> "ExitMessage":
        value = _json_object(payload, label="exit")
        if set(value) != {"returncode"} or not isinstance(value["returncode"], int):
            raise BrokerProtocolError("exit payload is invalid")
        return cls(returncode=value["returncode"])


@dataclass(frozen=True, slots=True)
class ErrorMessage:
    code: str
    message: str

    def __post_init__(self) -> None:
        if not _ERROR_CODE_PATTERN.fullmatch(self.code):
            raise BrokerProtocolError("broker error code is invalid")
        if (
            not self.message
            or len(self.message) > 200
            or any(character in self.message for character in "\r\n")
        ):
            raise BrokerProtocolError("broker error message is invalid")

    def to_payload(self) -> bytes:
        return _json_payload({"code": self.code, "message": self.message})

    @classmethod
    def from_payload(cls, payload: bytes) -> "ErrorMessage":
        value = _json_object(payload, label="error")
        if set(value) != {"code", "message"}:
            raise BrokerProtocolError("error payload is invalid")
        code = value["code"]
        message = value["message"]
        if not isinstance(code, str) or not isinstance(message, str):
            raise BrokerProtocolError("error payload fields must be strings")
        return cls(code=code, message=message)


async def read_frame(
    reader: asyncio.StreamReader, *, max_payload: int = MAX_FRAME_PAYLOAD
) -> BrokerFrame:
    try:
        header = await reader.readexactly(_FRAME_HEADER.size)
    except asyncio.IncompleteReadError as error:
        raise BrokerProtocolError("broker connection ended before a complete frame") from error
    kind_value, payload_size = _FRAME_HEADER.unpack(header)
    if payload_size > min(max_payload, MAX_FRAME_PAYLOAD):
        raise BrokerProtocolError("broker frame payload exceeds its limit")
    try:
        kind = FrameKind(kind_value)
    except ValueError as error:
        raise BrokerProtocolError("broker frame type is unknown") from error
    try:
        payload = await reader.readexactly(payload_size)
    except asyncio.IncompleteReadError as error:
        raise BrokerProtocolError("broker connection ended inside a frame") from error
    return BrokerFrame(kind=kind, payload=payload)


class FrameWriter:
    def __init__(self, writer: asyncio.StreamWriter) -> None:
        self._writer = writer
        self._lock = asyncio.Lock()

    async def send(self, kind: FrameKind, payload: bytes = b"") -> None:
        if len(payload) > MAX_FRAME_PAYLOAD:
            raise BrokerProtocolError("broker frame payload exceeds its limit")
        async with self._lock:
            self._writer.write(_FRAME_HEADER.pack(kind, len(payload)))
            self._writer.write(payload)
            await self._writer.drain()

    async def close(self) -> None:
        self._writer.close()
        await self._writer.wait_closed()


class BrokerStdin:
    def __init__(self, frames: FrameWriter) -> None:
        self._frames = frames
        self._pending: list[bytes] = []
        self._pending_bytes = 0
        self._lock = asyncio.Lock()
        self._closed = False

    def write(self, payload: bytes) -> None:
        if self._closed:
            raise BrokenPipeError("broker worker stdin is closed")
        if not isinstance(payload, bytes):
            raise TypeError("broker worker stdin requires bytes")
        if self._pending_bytes + len(payload) > MAX_BUFFERED_STDIN:
            raise BufferError("broker worker stdin buffer is full")
        for offset in range(0, len(payload), MAX_STREAM_CHUNK):
            self._pending.append(payload[offset : offset + MAX_STREAM_CHUNK])
        self._pending_bytes += len(payload)

    async def drain(self) -> None:
        async with self._lock:
            pending = self._pending
            self._pending = []
            self._pending_bytes = 0
            for chunk in pending:
                await self._frames.send(FrameKind.STDIN, chunk)

    def close(self) -> None:
        self._closed = True
        self._pending.clear()
        self._pending_bytes = 0


class BrokerWorkerProcess:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        frames: FrameWriter,
    ) -> None:
        self.stdin: BrokerStdin | None = BrokerStdin(frames)
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self._reader = reader
        self._writer = writer
        self._frames = frames
        self._returncode: int | None = None
        self._waiter: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        self._control_tasks: set[asyncio.Task[None]] = set()
        self._receiver = asyncio.create_task(self._receive())

    @property
    def returncode(self) -> int | None:
        return self._returncode

    async def wait(self) -> int:
        return await asyncio.shield(self._waiter)

    def terminate(self) -> None:
        if self._returncode is None:
            self._queue_control(FrameKind.TERMINATE)

    def kill(self) -> None:
        if self._returncode is None:
            self._queue_control(FrameKind.KILL)

    def _queue_control(self, kind: FrameKind) -> None:
        task = asyncio.create_task(self._send_control(kind))
        self._control_tasks.add(task)
        task.add_done_callback(self._control_tasks.discard)

    async def _send_control(self, kind: FrameKind) -> None:
        try:
            await self._frames.send(kind)
        except (BrokerProtocolError, ConnectionError):
            self._finish(125)

    async def _receive(self) -> None:
        returncode = 125
        try:
            while True:
                frame = await read_frame(self._reader)
                if frame.kind is FrameKind.STDOUT:
                    self.stdout.feed_data(frame.payload)
                elif frame.kind is FrameKind.STDERR:
                    self.stderr.feed_data(frame.payload)
                elif frame.kind is FrameKind.EXIT:
                    returncode = ExitMessage.from_payload(frame.payload).returncode
                    break
                elif frame.kind is FrameKind.ERROR:
                    error = ErrorMessage.from_payload(frame.payload)
                    self.stderr.feed_data(f"broker-error:{error.code}:{error.message}\n".encode())
                    break
                else:
                    raise BrokerProtocolError("broker sent a frame that is invalid after start")
        except (BrokerProtocolError, ConnectionError):
            self.stderr.feed_data(b"broker-error:protocol:worker connection failed\n")
        finally:
            self._finish(returncode)
            self.stdout.feed_eof()
            self.stderr.feed_eof()
            if self.stdin is not None:
                self.stdin.close()
                self.stdin = None
            self._writer.close()

    def _finish(self, returncode: int) -> None:
        if self._returncode is not None:
            return
        self._returncode = returncode
        if not self._waiter.done():
            self._waiter.set_result(returncode)


async def connect_broker_worker(
    socket_path: Path,
    request: StartRequest,
    *,
    timeout_seconds: float = 3.0,
) -> BrokerWorkerProcess:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(socket_path), timeout=timeout_seconds
        )
    except (TimeoutError, OSError) as error:
        raise BrokerUnavailableError("worker broker is unavailable") from error
    frames = FrameWriter(writer)
    try:
        await asyncio.wait_for(
            frames.send(FrameKind.START, request.to_payload()), timeout=timeout_seconds
        )
        response = await asyncio.wait_for(
            read_frame(reader, max_payload=MAX_CONTROL_PAYLOAD), timeout=timeout_seconds
        )
        if response.kind is FrameKind.ERROR:
            error = ErrorMessage.from_payload(response.payload)
            raise BrokerUnavailableError(f"worker broker rejected launch: {error.code}")
        if response.kind is not FrameKind.STARTED or response.payload:
            raise BrokerProtocolError("worker broker did not acknowledge start")
        return BrokerWorkerProcess(reader, writer, frames)
    except (TimeoutError, BrokerProtocolError, BrokerUnavailableError, ConnectionError):
        writer.close()
        await writer.wait_closed()
        raise


async def probe_broker(socket_path: Path, *, timeout_seconds: float = 1.0) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(socket_path), timeout=timeout_seconds
        )
        frames = FrameWriter(writer)
        await asyncio.wait_for(frames.send(FrameKind.PING), timeout=timeout_seconds)
        response = await asyncio.wait_for(
            read_frame(reader, max_payload=0), timeout=timeout_seconds
        )
        await frames.close()
        return response.kind is FrameKind.PONG and not response.payload
    except (TimeoutError, OSError, BrokerProtocolError, ConnectionError):
        return False
