# SPDX-License-Identifier: GPL-2.0-only

import asyncio
import os
import resource
import shutil
from collections import deque
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from .boards import BoardProfile
from .firmware import ValidatedFirmware, validate_and_pad_firmware, write_private_flash_image
from .framebuffer import RGBFrame, encode_framebuffer_packet, parse_qemu_ppm
from .gdb import GdbRemoteClient, GdbRemoteError
from .inputs import qmp_button_event, qmp_imu_sample, qmp_key_event, qmp_power_state
from .qemu import QemuWorkerConfig, build_qemu_command
from .qmp import QmpError, QmpUnavailableError, execute_qmp
from .settings import Settings


class SessionCapacityError(RuntimeError):
    pass


class SessionNotFoundError(KeyError):
    pass


class WorkerUnavailableError(RuntimeError):
    pass


class SessionTransitionError(RuntimeError):
    pass


class SessionState(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"
    EXPIRED = "expired"


ACTIVE_SESSION_STATES = frozenset(
    {SessionState.STARTING, SessionState.RUNNING, SessionState.PAUSED}
)
MAX_DEBUG_BREAKPOINTS = 32


@dataclass(slots=True, eq=False)
class SessionRecord:
    id: str
    board: BoardProfile
    firmware: ValidatedFirmware
    created_at: datetime
    expires_at: datetime
    runtime_directory: Path
    flash_path: Path
    qmp_socket_path: Path
    gdb_socket_path: Path
    state: SessionState = SessionState.STARTING
    exit_code: int | None = None
    process: asyncio.subprocess.Process | None = None
    reader_task: asyncio.Task[None] | None = None
    serial_buffer: deque[bytes] = field(default_factory=lambda: deque(maxlen=256))
    subscribers: set[asyncio.Queue[bytes | None]] = field(default_factory=set)
    qmp_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    gdb_client: GdbRemoteClient | None = None
    debug_run_task: asyncio.Task[None] | None = None
    debug_stop_reason: str | None = None
    debug_breakpoints: set[int] = field(default_factory=set)

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "board_id": self.board.id,
            "state": self.state,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "exit_code": self.exit_code,
            "firmware": asdict(self.firmware),
        }


def _limit_worker_resources(memory_limit_mib: int, cpu_limit_seconds: int) -> None:
    memory_bytes = memory_limit_mib * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit_seconds, cpu_limit_seconds + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    os.umask(0o077)


class SessionManager:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task[None] | None = None

    @property
    def worker_ready(self) -> bool:
        return (
            self._settings.native_workers_enabled
            and self._settings.qemu_executable.is_file()
            and self._settings.rom_directory.is_dir()
        )

    async def start(self) -> None:
        self._settings.runtime_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def close(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            await asyncio.gather(self._cleanup_task, return_exceptions=True)
        for session_id in tuple(self._sessions):
            await self.stop(session_id)

    async def create(self, board: BoardProfile, upload: bytes) -> SessionRecord:
        if not self.worker_ready:
            raise WorkerUnavailableError("native QEMU workers are not configured and enabled")

        async with self._lock:
            active_count = sum(
                session.state in ACTIVE_SESSION_STATES
                for session in self._sessions.values()
            )
            if active_count >= self._settings.max_concurrent_sessions:
                raise SessionCapacityError("all simulator workers are currently in use")

            flash_image, metadata = validate_and_pad_firmware(upload, board)
            now = datetime.now(UTC)
            session_id = uuid4().hex
            runtime_directory = self._settings.runtime_root / session_id
            flash_path = runtime_directory / "flash.bin"
            qmp_socket_path = runtime_directory / "qmp.sock"
            gdb_socket_path = runtime_directory / "gdb.sock"
            write_private_flash_image(flash_path, flash_image)

            session = SessionRecord(
                id=session_id,
                board=board,
                firmware=metadata,
                created_at=now,
                expires_at=now + timedelta(seconds=self._settings.session_ttl_seconds),
                runtime_directory=runtime_directory,
                flash_path=flash_path,
                qmp_socket_path=qmp_socket_path,
                gdb_socket_path=gdb_socket_path,
            )
            self._sessions[session_id] = session

        try:
            await self._launch(session)
        except Exception:
            session.state = SessionState.FAILED
            shutil.rmtree(runtime_directory, ignore_errors=True)
            raise
        return session

    def get(self, session_id: str) -> SessionRecord:
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise SessionNotFoundError(session_id) from error

    async def stop(self, session_id: str, *, expired: bool = False) -> SessionRecord:
        session = self.get(session_id)
        await self._close_debugger(session)
        process = session.process
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()
        if session.reader_task and session.reader_task is not asyncio.current_task():
            await asyncio.gather(session.reader_task, return_exceptions=True)
        session.exit_code = process.returncode if process else session.exit_code
        session.state = SessionState.EXPIRED if expired else SessionState.STOPPED
        self._publish(session, None)
        shutil.rmtree(session.runtime_directory, ignore_errors=True)
        return session

    async def write_serial(self, session_id: str, payload: bytes) -> None:
        session = self.get(session_id)
        process = session.process
        if session.state is not SessionState.RUNNING or not process or not process.stdin:
            raise RuntimeError("session serial input is not available")
        process.stdin.write(payload)
        await process.stdin.drain()

    async def send_key(self, session_id: str, key: str, pressed: bool) -> None:
        session = self.get(session_id)
        if session.state is not SessionState.RUNNING:
            raise RuntimeError("session board input is not available")
        if not self._settings.worker_qmp_enabled:
            raise QmpUnavailableError("QMP board input is disabled for this worker")

        arguments = qmp_key_event(session.board, key, pressed)
        async with session.qmp_lock:
            await execute_qmp(session.qmp_socket_path, "input-send-event", arguments)

    async def send_button(self, session_id: str, button: str, pressed: bool) -> None:
        session = self.get(session_id)
        self._require_board_input(session)
        arguments = qmp_button_event(session.board, button, pressed)
        async with session.qmp_lock:
            await execute_qmp(session.qmp_socket_path, "qom-set", arguments)

    async def set_imu_sample(
        self,
        session_id: str,
        acceleration_g: tuple[float, float, float],
        angular_velocity_dps: tuple[float, float, float],
    ) -> None:
        session = self.get(session_id)
        self._require_board_input(session)
        arguments = qmp_imu_sample(
            session.board, acceleration_g, angular_velocity_dps
        )
        async with session.qmp_lock:
            await execute_qmp(session.qmp_socket_path, "qom-set", arguments)

    async def set_power_state(
        self,
        session_id: str,
        battery_mv: int,
        vin_mv: int,
        charging: bool,
    ) -> None:
        session = self.get(session_id)
        self._require_board_input(session)
        arguments = qmp_power_state(session.board, battery_mv, vin_mv, charging)
        async with session.qmp_lock:
            await execute_qmp(session.qmp_socket_path, "qom-set", arguments)

    def _require_board_input(self, session: SessionRecord) -> None:
        if session.state is not SessionState.RUNNING:
            raise RuntimeError("session board input is not available")
        if not self._settings.worker_qmp_enabled:
            raise QmpUnavailableError("QMP board input is disabled for this worker")

    async def pause(self, session_id: str) -> SessionRecord:
        session = self.get(session_id)
        if not self._settings.worker_qmp_enabled:
            raise QmpUnavailableError("QMP session control is disabled for this worker")
        async with session.qmp_lock:
            if session.state is not SessionState.RUNNING:
                raise SessionTransitionError(f"cannot pause session in {session.state} state")
            await execute_qmp(session.qmp_socket_path, "stop")
            session.state = SessionState.PAUSED
        debug_run_task = session.debug_run_task
        if debug_run_task:
            try:
                await asyncio.wait_for(asyncio.shield(debug_run_task), timeout=2)
            except TimeoutError as error:
                debug_run_task.cancel()
                await asyncio.gather(debug_run_task, return_exceptions=True)
                if session.debug_run_task is debug_run_task:
                    session.debug_run_task = None
                if session.gdb_client:
                    await session.gdb_client.close()
                    session.gdb_client = None
                raise GdbRemoteError(
                    "debugger did not acknowledge the paused worker"
                ) from error
            if session.debug_stop_reason and session.debug_stop_reason.startswith(
                "debugger-error:"
            ):
                raise GdbRemoteError(session.debug_stop_reason)
        return session

    async def resume(self, session_id: str) -> SessionRecord:
        session = self.get(session_id)
        if not self._settings.worker_qmp_enabled:
            raise QmpUnavailableError("QMP session control is disabled for this worker")
        if session.state is not SessionState.PAUSED:
            raise SessionTransitionError(f"cannot resume session in {session.state} state")
        if session.gdb_client:
            session.state = SessionState.RUNNING
            session.debug_stop_reason = None
            session.debug_run_task = asyncio.create_task(self._continue_under_debugger(session))
        else:
            async with session.qmp_lock:
                await execute_qmp(session.qmp_socket_path, "cont")
                session.state = SessionState.RUNNING
        return session

    async def refresh_state(self, session_id: str) -> SessionRecord:
        session = self.get(session_id)
        if (
            session.state not in {SessionState.RUNNING, SessionState.PAUSED}
            or not self._settings.worker_qmp_enabled
        ):
            return session
        async with session.qmp_lock:
            status = await execute_qmp(session.qmp_socket_path, "query-status")
        if isinstance(status, dict):
            session.state = SessionState.RUNNING if status.get("running") else SessionState.PAUSED
        return session

    async def debug_registers(self, session_id: str) -> dict[str, int | None]:
        session = await self._require_paused_debug_session(session_id)
        client = await self._debug_client(session)
        return await client.read_registers()

    async def debug_read_memory(self, session_id: str, address: int, length: int) -> bytes:
        session = await self._require_paused_debug_session(session_id)
        client = await self._debug_client(session)
        return await client.read_memory(address, length)

    async def debug_set_breakpoint(self, session_id: str, address: int, enabled: bool) -> None:
        session = await self._require_paused_debug_session(session_id)
        client = await self._debug_client(session)
        if enabled:
            if (
                address not in session.debug_breakpoints
                and len(session.debug_breakpoints) >= MAX_DEBUG_BREAKPOINTS
            ):
                raise GdbRemoteError(
                    f"a session may have at most {MAX_DEBUG_BREAKPOINTS} breakpoints"
                )
            await client.add_breakpoint(address)
            session.debug_breakpoints.add(address)
        else:
            await client.remove_breakpoint(address)
            session.debug_breakpoints.discard(address)

    async def debug_step(self, session_id: str) -> str:
        session = await self._require_paused_debug_session(session_id)
        reply = await (await self._debug_client(session)).step()
        session.debug_stop_reason = reply
        return reply

    async def _require_paused_debug_session(self, session_id: str) -> SessionRecord:
        session = await self.refresh_state(session_id)
        if session.state is not SessionState.PAUSED:
            raise SessionTransitionError("debug operations require a paused session")
        if not (
            self._settings.worker_debug_enabled
            and self._settings.worker_qmp_enabled
        ):
            raise GdbRemoteError("private GDB worker access is disabled")
        return session

    async def _debug_client(self, session: SessionRecord) -> GdbRemoteClient:
        if session.gdb_client is None:
            session.gdb_client = await GdbRemoteClient.connect(session.gdb_socket_path)
        return session.gdb_client

    async def _continue_under_debugger(self, session: SessionRecord) -> None:
        try:
            if session.gdb_client is None:
                raise GdbRemoteError("debugger is not connected")
            session.debug_stop_reason = await session.gdb_client.continue_execution()
            if session.state is SessionState.RUNNING:
                session.state = SessionState.PAUSED
        except GdbRemoteError as error:
            session.debug_stop_reason = f"debugger-error: {error}"
            with suppress(QmpError):
                await self.refresh_state(session.id)
            client = session.gdb_client
            session.gdb_client = None
            if client:
                await client.close()
        finally:
            session.debug_run_task = None

    async def _close_debugger(self, session: SessionRecord) -> None:
        task = session.debug_run_task
        session.debug_run_task = None
        if task and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        client = session.gdb_client
        session.gdb_client = None
        if client:
            await client.close()

    async def reset(self, session_id: str) -> SessionRecord:
        session = self.get(session_id)
        if not self._settings.worker_qmp_enabled:
            raise QmpUnavailableError("QMP session control is disabled for this worker")
        async with session.qmp_lock:
            if session.state not in {SessionState.RUNNING, SessionState.PAUSED}:
                raise SessionTransitionError(f"cannot reset session in {session.state} state")
            await execute_qmp(session.qmp_socket_path, "system_reset")
        return session

    async def capture_framebuffer(self, session_id: str) -> RGBFrame:
        session = self.get(session_id)
        if session.state not in {SessionState.RUNNING, SessionState.PAUSED}:
            raise RuntimeError("session framebuffer is not available")
        if not self._settings.worker_qmp_enabled:
            raise QmpUnavailableError("QMP framebuffer capture is disabled for this worker")

        screenshot_path = session.runtime_directory / "framebuffer.ppm"
        async with session.qmp_lock:
            try:
                await execute_qmp(
                    session.qmp_socket_path,
                    "screendump",
                    {"filename": str(screenshot_path)},
                )
                return parse_qemu_ppm(screenshot_path.read_bytes())
            finally:
                screenshot_path.unlink(missing_ok=True)

    async def subscribe_framebuffer(self, session_id: str) -> AsyncIterator[bytes]:
        session = self.get(session_id)
        previous_pixels: bytes | None = None
        sequence = 0
        interval_seconds = max(self._settings.framebuffer_interval_ms, 16) / 1000

        while session.state in {SessionState.RUNNING, SessionState.PAUSED}:
            frame = await self.capture_framebuffer(session_id)
            if frame.pixels != previous_pixels:
                yield encode_framebuffer_packet(frame, sequence)
                previous_pixels = frame.pixels
                sequence = (sequence + 1) & 0xFFFFFFFF
            await asyncio.sleep(interval_seconds)

    async def subscribe_serial(self, session_id: str) -> AsyncIterator[bytes]:
        session = self.get(session_id)
        for chunk in session.serial_buffer:
            yield chunk
        if session.state not in {SessionState.RUNNING, SessionState.PAUSED}:
            return

        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=128)
        session.subscribers.add(queue)
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    return
                yield chunk
        finally:
            session.subscribers.discard(queue)

    async def _launch(self, session: SessionRecord) -> None:
        worker_config = QemuWorkerConfig(
            executable=self._settings.qemu_executable,
            rom_directory=self._settings.rom_directory,
        )
        worker_config.validate()
        command = build_qemu_command(
            worker_config,
            session.board,
            session.flash_path,
            session.qmp_socket_path if self._settings.worker_qmp_enabled else None,
            (
                session.gdb_socket_path
                if self._settings.worker_debug_enabled
                and self._settings.worker_qmp_enabled
                else None
            ),
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=session.runtime_directory,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            start_new_session=True,
            preexec_fn=lambda: _limit_worker_resources(
                self._settings.worker_memory_limit_mib,
                self._settings.worker_cpu_limit_seconds,
            ),
        )
        session.process = process
        session.state = SessionState.RUNNING
        session.reader_task = asyncio.create_task(self._read_serial(session))

    async def _read_serial(self, session: SessionRecord) -> None:
        process = session.process
        if not process or not process.stdout:
            return
        while chunk := await process.stdout.read(4096):
            session.serial_buffer.append(chunk)
            self._publish(session, chunk)
        session.exit_code = await process.wait()
        await self._close_debugger(session)
        if session.state in {SessionState.RUNNING, SessionState.PAUSED}:
            session.state = SessionState.STOPPED if session.exit_code == 0 else SessionState.FAILED
        self._publish(session, None)
        shutil.rmtree(session.runtime_directory, ignore_errors=True)

    @staticmethod
    def _publish(session: SessionRecord, chunk: bytes | None) -> None:
        for queue in tuple(session.subscribers):
            try:
                queue.put_nowait(chunk)
            except asyncio.QueueFull:
                session.subscribers.discard(queue)

    async def _cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(5)
                now = datetime.now(UTC)
                expired_ids = [
                    session.id
                    for session in self._sessions.values()
                    if session.state in ACTIVE_SESSION_STATES
                    and session.expires_at <= now
                ]
                for session_id in expired_ids:
                    await self.stop(session_id, expired=True)
        except asyncio.CancelledError:
            raise
