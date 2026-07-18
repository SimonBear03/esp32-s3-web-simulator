# SPDX-License-Identifier: GPL-2.0-only

import asyncio
import string
import xml.etree.ElementTree as ET
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


class GdbRemoteError(RuntimeError):
    """Raised when the private QEMU GDB remote endpoint cannot satisfy a request."""


@dataclass(frozen=True, slots=True)
class RegisterDefinition:
    name: str
    number: int
    bitsize: int


# Espressif's ESP32-S3 Xtensa GDB stub does not currently advertise target
# descriptions through qXfer.  These stable core register numbers mirror the
# pinned QEMU source at target/xtensa/core-esp32s3/gdb-config.inc.c.  Keep the
# fallback deliberately smaller than the full TIE register map so it remains a
# useful, predictable browser-debugging surface.
_ESP32_S3_CORE_REGISTERS = (
    RegisterDefinition("pc", 0, 32),
    *(RegisterDefinition(f"ar{index}", index + 1, 32) for index in range(64)),
    RegisterDefinition("lbeg", 65, 32),
    RegisterDefinition("lend", 66, 32),
    RegisterDefinition("lcount", 67, 32),
    RegisterDefinition("sar", 68, 6),
    RegisterDefinition("windowbase", 69, 4),
    RegisterDefinition("windowstart", 70, 16),
    RegisterDefinition("configid0", 71, 32),
    RegisterDefinition("configid1", 72, 32),
    RegisterDefinition("ps", 73, 19),
    RegisterDefinition("threadptr", 74, 32),
    RegisterDefinition("br", 75, 16),
    RegisterDefinition("scompare1", 76, 32),
    RegisterDefinition("acclo", 77, 32),
    RegisterDefinition("acchi", 78, 8),
    RegisterDefinition("m0", 79, 32),
    RegisterDefinition("m1", 80, 32),
    RegisterDefinition("m2", 81, 32),
    RegisterDefinition("m3", 82, 32),
    RegisterDefinition("gpio_out", 83, 8),
)


def _checksum(payload: bytes) -> bytes:
    return f"{sum(payload) & 0xFF:02x}".encode()


def _decode_payload(payload: bytes) -> bytes:
    decoded = bytearray()
    index = 0
    while index < len(payload):
        value = payload[index]
        if value == ord("}"):
            index += 1
            if index >= len(payload):
                raise GdbRemoteError("GDB returned a truncated escape sequence")
            decoded.append(payload[index] ^ 0x20)
        elif value == ord("*"):
            index += 1
            if not decoded or index >= len(payload):
                raise GdbRemoteError("GDB returned invalid run-length encoding")
            decoded.extend([decoded[-1]] * (payload[index] - 29))
        else:
            decoded.append(value)
        index += 1
    return bytes(decoded)


class GdbRemoteClient:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._lock = asyncio.Lock()
        self._no_ack = False
        self._supports_target_xml = False
        self._registers: tuple[RegisterDefinition, ...] | None = None

    @classmethod
    async def connect(cls, socket_path: Path, *, timeout_seconds: float = 2) -> "GdbRemoteClient":
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        last_error: OSError | None = None
        while loop.time() < deadline:
            client: GdbRemoteClient | None = None
            try:
                reader, writer = await asyncio.open_unix_connection(socket_path)
                client = cls(reader, writer)
                await client._negotiate()
                return client
            except OSError as error:
                last_error = error
                if client is not None:
                    await client.close()
                await asyncio.sleep(0.05)
            except BaseException:
                if client is not None:
                    await client.close()
                raise
        raise GdbRemoteError(f"GDB socket is unavailable: {socket_path}") from last_error

    async def close(self) -> None:
        if not self._writer.is_closing():
            self._writer.close()
            with suppress(ConnectionError):
                await self._writer.wait_closed()

    async def _negotiate(self) -> None:
        supported = await self.command("qSupported:multiprocess+;qRelocInsn+")
        self._supports_target_xml = "qXfer:features:read+" in supported
        if "QStartNoAckMode+" in supported:
            if await self.command("QStartNoAckMode") != "OK":
                raise GdbRemoteError("QEMU rejected GDB no-ack mode")
            self._no_ack = True

    async def command(self, payload: str, *, timeout_seconds: float | None = 2) -> str:
        async with self._lock:
            try:
                if timeout_seconds is None:
                    return await self._command_unlocked(payload)
                async with asyncio.timeout(timeout_seconds):
                    return await self._command_unlocked(payload)
            except TimeoutError as error:
                raise GdbRemoteError(f"GDB command timed out: {payload[:32]}") from error
            except (asyncio.IncompleteReadError, ConnectionError) as error:
                raise GdbRemoteError("QEMU closed the private GDB connection") from error

    async def _command_unlocked(self, payload: str) -> str:
        encoded = payload.encode("ascii")
        self._writer.write(b"$" + encoded + b"#" + _checksum(encoded))
        await self._writer.drain()
        if not self._no_ack:
            acknowledgement = await self._reader.readexactly(1)
            if acknowledgement != b"+":
                raise GdbRemoteError("QEMU did not acknowledge the GDB request")

        while True:
            response = await self._read_packet()
            if not (
                response.startswith("O")
                and len(response) > 1
                and len(response[1:]) % 2 == 0
                and all(character in string.hexdigits for character in response[1:])
            ):
                return response

    async def _read_packet(self) -> str:
        while True:
            marker = await self._reader.readexactly(1)
            if marker == b"$":
                break
            if marker == b"-":
                raise GdbRemoteError("QEMU rejected the GDB request checksum")

        encoded = await self._reader.readuntil(b"#")
        encoded = encoded[:-1]
        expected_checksum = await self._reader.readexactly(2)
        if _checksum(encoded).lower() != expected_checksum.lower():
            if not self._no_ack:
                self._writer.write(b"-")
                await self._writer.drain()
            raise GdbRemoteError("QEMU returned a GDB packet with a bad checksum")
        if not self._no_ack:
            self._writer.write(b"+")
            await self._writer.drain()
        try:
            return _decode_payload(encoded).decode("utf-8")
        except UnicodeDecodeError as error:
            raise GdbRemoteError("QEMU returned non-text GDB packet data") from error

    async def _read_annex(self, annex: str) -> bytes:
        result = bytearray()
        while True:
            response = await self.command(f"qXfer:features:read:{annex}:{len(result):x},1000")
            if not response or response[0] not in {"m", "l"}:
                raise GdbRemoteError(f"QEMU rejected GDB feature annex: {annex}")
            result.extend(response[1:].encode())
            if response[0] == "l":
                return bytes(result)

    async def register_definitions(self) -> tuple[RegisterDefinition, ...]:
        if self._registers is not None:
            return self._registers

        if not self._supports_target_xml:
            self._registers = _ESP32_S3_CORE_REGISTERS
            return self._registers

        pending = ["target.xml"]
        visited: set[str] = set()
        registers: list[RegisterDefinition] = []
        next_number = 0
        while pending:
            annex = pending.pop(0)
            if annex in visited:
                continue
            visited.add(annex)
            try:
                root = ET.fromstring(await self._read_annex(annex))
            except ET.ParseError as error:
                raise GdbRemoteError(f"QEMU returned invalid register XML: {annex}") from error
            for element in root.iter():
                local_name = element.tag.rsplit("}", 1)[-1]
                if local_name == "include" and (href := element.get("href")):
                    pending.append(href)
                if local_name != "reg":
                    continue
                name = element.get("name")
                bitsize = element.get("bitsize")
                if not name or not bitsize:
                    continue
                number = int(element.get("regnum", next_number))
                registers.append(RegisterDefinition(name, number, int(bitsize)))
                next_number = number + 1
                if len(registers) > 256:
                    raise GdbRemoteError("QEMU exposed too many GDB registers")
        if not registers:
            raise GdbRemoteError("QEMU exposed no GDB registers")
        self._registers = tuple(registers)
        return self._registers

    async def read_registers(self) -> dict[str, int | None]:
        result: dict[str, int | None] = {}
        for register in await self.register_definitions():
            value = await self.command(f"p{register.number:x}")
            if not value or value.startswith("E") or set(value.lower()) == {"x"}:
                result[register.name] = None
                continue
            try:
                raw = bytes.fromhex(value)
            except ValueError as error:
                raise GdbRemoteError(
                    f"QEMU returned invalid data for register {register.name}"
                ) from error
            result[register.name] = int.from_bytes(raw, "little")
        return result

    async def read_memory(self, address: int, length: int) -> bytes:
        if not 0 <= address <= 0xFFFFFFFF:
            raise GdbRemoteError("debug address must fit in 32 bits")
        if not 1 <= length <= 4096:
            raise GdbRemoteError("debug memory reads must be between 1 and 4096 bytes")
        response = await self.command(f"m{address:x},{length:x}")
        if response.startswith("E"):
            raise GdbRemoteError(f"QEMU could not read guest memory: {response}")
        try:
            data = bytes.fromhex(response)
        except ValueError as error:
            raise GdbRemoteError("QEMU returned invalid guest memory data") from error
        if len(data) != length:
            raise GdbRemoteError("QEMU returned a short guest memory read")
        return data

    async def add_breakpoint(self, address: int) -> None:
        await self._set_breakpoint(address, True)

    async def remove_breakpoint(self, address: int) -> None:
        await self._set_breakpoint(address, False)

    async def _set_breakpoint(self, address: int, enabled: bool) -> None:
        if not 0 <= address <= 0xFFFFFFFF:
            raise GdbRemoteError("breakpoint address must fit in 32 bits")
        operation = "Z" if enabled else "z"
        if await self.command(f"{operation}1,{address:x},1") != "OK":
            action = "add" if enabled else "remove"
            raise GdbRemoteError(f"QEMU could not {action} the breakpoint")

    async def step(self) -> str:
        response = await self.command("s")
        if not response.startswith(("S", "T")):
            raise GdbRemoteError(f"QEMU returned an invalid step stop reply: {response}")
        return response

    async def continue_execution(self) -> str:
        response = await self.command("c", timeout_seconds=None)
        if not response.startswith(("S", "T", "W", "X")):
            raise GdbRemoteError(f"QEMU returned an invalid stop reply: {response}")
        return response
