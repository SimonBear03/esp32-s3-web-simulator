# SPDX-License-Identifier: GPL-2.0-only

import asyncio
import json
from pathlib import Path
from typing import Any


class QmpError(RuntimeError):
    """Raised when QEMU's machine protocol cannot complete a request."""


class QmpUnavailableError(QmpError):
    pass


class QmpCommandError(QmpError):
    pass


async def _read_message(reader: asyncio.StreamReader) -> dict[str, Any]:
    while raw := await reader.readline():
        if not raw.strip():
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError as error:
            raise QmpError("QEMU returned invalid QMP JSON") from error
        if not isinstance(message, dict):
            raise QmpError("QEMU returned a non-object QMP message")
        return message
    raise QmpUnavailableError("QEMU closed the QMP connection")


async def _read_response(reader: asyncio.StreamReader, request_id: str) -> Any:
    while True:
        message = await _read_message(reader)
        if message.get("id") != request_id:
            continue
        if error := message.get("error"):
            description = (
                error.get("desc", "QMP command failed")
                if isinstance(error, dict)
                else str(error)
            )
            raise QmpCommandError(description)
        return message.get("return")


async def _open_qmp(
    socket_path: Path, timeout_seconds: float
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    last_error: OSError | None = None

    while loop.time() < deadline:
        try:
            return await asyncio.open_unix_connection(socket_path)
        except OSError as error:
            last_error = error
            await asyncio.sleep(0.05)
    raise QmpUnavailableError(f"QMP socket is unavailable: {socket_path}") from last_error


async def execute_qmp(
    socket_path: Path,
    command: str,
    arguments: dict[str, Any] | None = None,
    *,
    timeout_seconds: float = 2,
) -> Any:
    """Execute one QMP command over a private worker socket."""

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    reader, writer = await _open_qmp(socket_path, timeout_seconds)
    try:
        async with asyncio.timeout(timeout_seconds):
            greeting = await _read_message(reader)
            if "QMP" not in greeting:
                raise QmpError("QEMU did not send a QMP greeting")

            capabilities_id = "capabilities"
            writer.write(
                json.dumps(
                    {"execute": "qmp_capabilities", "id": capabilities_id},
                    separators=(",", ":"),
                ).encode()
                + b"\n"
            )
            await writer.drain()
            await _read_response(reader, capabilities_id)

            command_id = "command"
            request: dict[str, Any] = {"execute": command, "id": command_id}
            if arguments is not None:
                request["arguments"] = arguments
            writer.write(json.dumps(request, separators=(",", ":")).encode() + b"\n")
            await writer.drain()
            return await _read_response(reader, command_id)
    except TimeoutError as error:
        raise QmpUnavailableError(f"QMP command timed out: {command}") from error
    finally:
        # A QMP request is complete once its matching response has arrived.  Do
        # not await the peer side of this one-shot UNIX connection: QEMU may
        # reset it immediately after accepting an input event, and asyncio then
        # re-raises that peer reset from wait_closed() as if the command failed.
        writer.close()
