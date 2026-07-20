# SPDX-License-Identifier: GPL-2.0-only

import asyncio
import logging
import os
import resource
import shutil
import stat
import time
from collections import deque
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from .boards import BoardProfile
from .broker_protocol import (
    BrokerProtocolError,
    BrokerUnavailableError,
    StartRequest,
    connect_broker_worker,
    probe_broker,
)
from .firmware import ValidatedFirmware, validate_and_pad_firmware, write_private_flash_image
from .framebuffer import RGBFrame, encode_framebuffer_packet, parse_qemu_ppm
from .gdb import GdbRemoteClient, GdbRemoteError
from .inputs import qmp_button_event, qmp_imu_sample, qmp_key_event, qmp_power_state
from .qemu import QemuWorkerConfig, WorkerSandboxMode, build_qemu_command
from .qmp import QmpError, QmpUnavailableError, execute_qmp
from .recording import ReplayAction, SessionEvent, serial_metadata
from .settings import Settings
from .tracing import TRACE_EVENT_LIMITS, parse_worker_trace_line
from .worker_process import WorkerProcess

logger = logging.getLogger(__name__)


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
    POWERED_OFF = "powered_off"
    STOPPED = "stopped"
    FAILED = "failed"
    EXPIRED = "expired"


ACTIVE_SESSION_STATES = frozenset(
    {
        SessionState.STARTING,
        SessionState.RUNNING,
        SessionState.PAUSED,
        SessionState.POWERED_OFF,
    }
)
MAX_DEBUG_BREAKPOINTS = 32
MAX_UNIX_SOCKET_PATH_BYTES = 107
TRACE_READER_YIELD_LINES = 64


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
    initial_flash_image: bytes = field(default=b"", repr=False)
    state: SessionState = SessionState.STARTING
    exit_code: int | None = None
    process: WorkerProcess | None = None
    reader_task: asyncio.Task[None] | None = None
    trace_reader_task: asyncio.Task[None] | None = None
    serial_buffer: deque[bytes] = field(default_factory=lambda: deque(maxlen=256))
    subscribers: set[asyncio.Queue[bytes | None]] = field(default_factory=set)
    lifecycle_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    qmp_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    gdb_client: GdbRemoteClient | None = None
    debug_run_task: asyncio.Task[None] | None = None
    debug_stop_reason: str | None = None
    debug_breakpoints: set[int] = field(default_factory=set)
    generation: int = 1
    generation_started_ns: int = field(default_factory=time.monotonic_ns)
    next_event_sequence: int = 1
    events: deque[SessionEvent] = field(default_factory=deque)
    events_dropped: int = 0
    replay_actions: deque[ReplayAction] = field(default_factory=deque, repr=False)
    replay_actions_dropped: int = 0
    replay_task: asyncio.Task[None] | None = field(default=None, repr=False)
    replay_status: str = "idle"
    replay_error: str | None = None
    replay_speed: float | None = None
    accept_live_input: bool = True
    serial_output_bytes: int = 0
    trace_events_recorded: int = 0
    trace_events_dropped: int = 0
    trace_event_counts: dict[str, int] = field(default_factory=dict, repr=False)
    trace_truncation_reported: bool = False
    virtual_imu_state: tuple[
        tuple[float, float, float], tuple[float, float, float]
    ] | None = field(default=None, repr=False)
    virtual_power_state: tuple[int, int, bool] | None = field(default=None, repr=False)

    def public_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "board_id": self.board.id,
            "state": self.state,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "exit_code": self.exit_code,
            "firmware": asdict(self.firmware),
            "generation": self.generation,
            "recording": {
                "event_count": len(self.events),
                "events_dropped": self.events_dropped,
                "replayable_action_count": len(self.replay_actions),
                "replayable_actions_dropped": self.replay_actions_dropped,
                "trace_events_recorded": self.trace_events_recorded,
                "trace_events_dropped": self.trace_events_dropped,
            },
            "replay": {
                "status": self.replay_status,
                "speed": self.replay_speed,
                "error": self.replay_error,
            },
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
        if not self._settings.native_workers_enabled:
            return False
        if (
            self._settings.worker_sandbox_mode is WorkerSandboxMode.OCI_BROKER
            and self._settings.worker_shared_group_gid is None
        ):
            return False
        try:
            self._worker_config().validate()
        except FileNotFoundError:
            return False
        return True

    @property
    def worker_sandbox_mode(self) -> str:
        return self._settings.worker_sandbox_mode.value

    async def worker_is_ready(self) -> bool:
        if not self.worker_ready:
            return False
        if self._settings.worker_sandbox_mode is WorkerSandboxMode.OCI_BROKER:
            return await probe_broker(self._settings.worker_broker_socket)
        return True

    def _worker_config(self) -> QemuWorkerConfig:
        return QemuWorkerConfig(
            executable=self._settings.qemu_executable,
            rom_directory=self._settings.rom_directory,
            sandbox_mode=self._settings.worker_sandbox_mode,
            sandbox_executable=self._settings.worker_sandbox_executable,
            sandbox_readonly_paths=self._settings.worker_sandbox_readonly_paths,
            broker_socket_path=self._settings.worker_broker_socket,
        )

    async def start(self) -> None:
        if self._settings.native_workers_enabled and self._settings.worker_qmp_enabled:
            socket_paths = [
                self._settings.runtime_root / ("0" * 32) / "qmp.sock",
            ]
            if self._settings.worker_debug_enabled:
                socket_paths.append(self._settings.runtime_root / ("0" * 32) / "gdb.sock")
            if any(
                len(os.fsencode(str(path.absolute()))) > MAX_UNIX_SOCKET_PATH_BYTES
                for path in socket_paths
            ):
                raise WorkerUnavailableError(
                    "simulator runtime root is too long for private worker sockets"
                )
        self._settings.runtime_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        runtime_root_stat = self._settings.runtime_root.lstat()
        if not stat.S_ISDIR(runtime_root_stat.st_mode) or runtime_root_stat.st_uid != os.getuid():
            raise WorkerUnavailableError("simulator runtime root ownership is unsafe")
        if (
            self._settings.worker_sandbox_mode is WorkerSandboxMode.OCI_BROKER
            and self._settings.worker_shared_group_gid is not None
        ):
            os.chown(self._settings.runtime_root, -1, self._settings.worker_shared_group_gid)
            self._settings.runtime_root.chmod(0o2770)
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def close(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            await asyncio.gather(self._cleanup_task, return_exceptions=True)
        for session_id in tuple(self._sessions):
            await self.stop(session_id)

    async def create(self, board: BoardProfile, upload: bytes) -> SessionRecord:
        if not await self.worker_is_ready():
            raise WorkerUnavailableError("native QEMU workers are not configured and enabled")

        async with self._lock:
            active_count = sum(
                session.state in ACTIVE_SESSION_STATES for session in self._sessions.values()
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
            shared_group_gid = (
                self._settings.worker_shared_group_gid
                if self._settings.worker_sandbox_mode is WorkerSandboxMode.OCI_BROKER
                else None
            )
            write_private_flash_image(
                flash_path,
                flash_image,
                directory_mode=0o2770 if shared_group_gid is not None else 0o700,
                file_mode=0o660 if shared_group_gid is not None else 0o600,
                group_gid=shared_group_gid,
            )

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
                initial_flash_image=flash_image,
            )
            self._sessions[session_id] = session

        try:
            session.generation_started_ns = time.monotonic_ns()
            await self._launch(session)
            self._record_event(session, "lifecycle", "session.started", "service")
        except Exception:
            session.state = SessionState.FAILED
            shutil.rmtree(runtime_directory, ignore_errors=True)
            self._clear_private_session_data(session)
            raise
        return session

    def get(self, session_id: str) -> SessionRecord:
        try:
            return self._sessions[session_id]
        except KeyError as error:
            raise SessionNotFoundError(session_id) from error

    async def stop(self, session_id: str, *, expired: bool = False) -> SessionRecord:
        session = self.get(session_id)
        replay_task = session.replay_task
        session.replay_task = None
        if replay_task and replay_task is not asyncio.current_task():
            replay_task.cancel()
            await asyncio.gather(replay_task, return_exceptions=True)
        async with session.lifecycle_lock:
            await self._terminate_worker(session)
            self._clear_private_session_data(session)
            session.state = SessionState.EXPIRED if expired else SessionState.STOPPED
            self._record_event(
                session,
                "lifecycle",
                "session.expired" if expired else "session.stopped",
                "service",
            )
            self._publish(session, None)
            shutil.rmtree(session.runtime_directory, ignore_errors=True)
        return session

    async def write_serial(self, session_id: str, payload: bytes) -> None:
        session = self.get(session_id)
        self._require_live_input(session)
        process = session.process
        if session.state is not SessionState.RUNNING or not process or not process.stdin:
            raise RuntimeError("session serial input is not available")
        process.stdin.write(payload)
        await process.stdin.drain()
        self._record_input(
            session,
            ReplayAction(self._offset_ms(session), "serial", payload),
            serial_metadata(payload),
        )

    async def send_key(self, session_id: str, key: str, pressed: bool) -> None:
        session = self.get(session_id)
        self._require_live_input(session)
        if session.state is not SessionState.RUNNING:
            raise RuntimeError("session board input is not available")
        if not self._settings.worker_qmp_enabled:
            raise QmpUnavailableError("QMP board input is disabled for this worker")

        arguments = qmp_key_event(session.board, key, pressed)
        async with session.qmp_lock:
            await execute_qmp(session.qmp_socket_path, "input-send-event", arguments)
        self._record_input(
            session,
            ReplayAction(self._offset_ms(session), "key", (key, pressed)),
            {"key": key, "pressed": pressed},
        )

    async def send_button(self, session_id: str, button: str, pressed: bool) -> None:
        session = self.get(session_id)
        self._require_board_input(session)
        arguments = qmp_button_event(session.board, button, pressed)
        async with session.qmp_lock:
            await execute_qmp(session.qmp_socket_path, "qom-set", arguments)
        self._record_input(
            session,
            ReplayAction(self._offset_ms(session), "button", (button, pressed)),
            {"button": button, "pressed": pressed},
        )

    async def set_imu_sample(
        self,
        session_id: str,
        acceleration_g: tuple[float, float, float],
        angular_velocity_dps: tuple[float, float, float],
    ) -> None:
        session = self.get(session_id)
        self._require_board_input(session)
        arguments = qmp_imu_sample(session.board, acceleration_g, angular_velocity_dps)
        async with session.qmp_lock:
            await execute_qmp(session.qmp_socket_path, "qom-set", arguments)
        session.virtual_imu_state = (acceleration_g, angular_velocity_dps)
        self._record_input(
            session,
            ReplayAction(
                self._offset_ms(session),
                "imu",
                (acceleration_g, angular_velocity_dps),
            ),
            {
                "acceleration_g": self._vector_dict(acceleration_g),
                "angular_velocity_dps": self._vector_dict(angular_velocity_dps),
            },
        )

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
        session.virtual_power_state = (battery_mv, vin_mv, charging)
        self._record_input(
            session,
            ReplayAction(
                self._offset_ms(session),
                "power",
                (battery_mv, vin_mv, charging),
            ),
            {"battery_mv": battery_mv, "vin_mv": vin_mv, "charging": charging},
        )

    def _require_live_input(self, session: SessionRecord) -> None:
        if not session.accept_live_input:
            raise RuntimeError("live input is disabled while a replay is running")

    def _require_board_input(self, session: SessionRecord) -> None:
        self._require_live_input(session)
        if session.state is not SessionState.RUNNING:
            raise RuntimeError("session board input is not available")
        if not self._settings.worker_qmp_enabled:
            raise QmpUnavailableError("QMP board input is disabled for this worker")

    async def pause(self, session_id: str) -> SessionRecord:
        session = self.get(session_id)
        self._require_live_input(session)
        if not self._settings.worker_qmp_enabled:
            raise QmpUnavailableError("QMP session control is disabled for this worker")
        async with session.qmp_lock:
            if session.state is not SessionState.RUNNING:
                raise SessionTransitionError(f"cannot pause session in {session.state} state")
            await execute_qmp(session.qmp_socket_path, "stop")
            session.state = SessionState.PAUSED
        self._record_event(session, "control", "session.paused", "user")
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
                raise GdbRemoteError("debugger did not acknowledge the paused worker") from error
            if session.debug_stop_reason and session.debug_stop_reason.startswith(
                "debugger-error:"
            ):
                raise GdbRemoteError(session.debug_stop_reason)
        return session

    async def resume(self, session_id: str) -> SessionRecord:
        session = self.get(session_id)
        self._require_live_input(session)
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
        self._record_event(session, "control", "session.resumed", "user")
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
        if not (self._settings.worker_debug_enabled and self._settings.worker_qmp_enabled):
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
        self._require_live_input(session)
        if not self._settings.worker_qmp_enabled:
            raise QmpUnavailableError("QMP session control is disabled for this worker")
        async with session.qmp_lock:
            if session.state not in {SessionState.RUNNING, SessionState.PAUSED}:
                raise SessionTransitionError(f"cannot reset session in {session.state} state")
            await execute_qmp(session.qmp_socket_path, "system_reset")
        action = ReplayAction(self._offset_ms(session), "reset", None)
        self._append_replay_action(session, action)
        self._record_event(session, "control", "session.reset", "user")
        return session

    async def power_off(self, session_id: str) -> SessionRecord:
        session = self.get(session_id)
        async with session.lifecycle_lock:
            self._require_live_input(session)
            if session.state not in {SessionState.RUNNING, SessionState.PAUSED}:
                raise SessionTransitionError(
                    f"cannot power off session in {session.state} state"
                )
            action = ReplayAction(self._offset_ms(session), "power_off", None)
            await self._power_off_worker(session)
            self._append_replay_action(session, action)
            self._record_event(session, "control", "session.powered_off", "user")
        return session

    async def power_on(self, session_id: str) -> SessionRecord:
        session = self.get(session_id)
        async with session.lifecycle_lock:
            self._require_live_input(session)
            if session.state is not SessionState.POWERED_OFF:
                raise SessionTransitionError(
                    f"cannot power on session in {session.state} state"
                )
            action = ReplayAction(self._offset_ms(session), "power_on", None)
            await self._power_on_worker(session)
            self._append_replay_action(session, action)
            self._record_event(session, "control", "session.powered_on", "user")
        return session

    def list_events(
        self, session_id: str, *, after: int = 0, limit: int = 200
    ) -> dict[str, object]:
        session = self.get(session_id)
        bounded_limit = min(max(limit, 1), self._settings.max_event_page_size)
        events = [event for event in session.events if event.sequence > after][:bounded_limit]
        first_sequence = session.events[0].sequence if session.events else None
        return {
            "session_id": session.id,
            "generation": session.generation,
            "events_dropped": session.events_dropped,
            "cursor_truncated": bool(first_sequence is not None and after < first_sequence - 1),
            "events": [event.public_dict() for event in events],
            "next_after": events[-1].sequence if events else after,
        }

    def diagnostics(self, session_id: str) -> dict[str, object]:
        session = self.get(session_id)
        serial_tail = b"".join(session.serial_buffer)
        return {
            "schema": "esp32-s3-simulator-diagnostics/v1",
            "privacy": {
                "firmware_bytes_included": False,
                "mutated_flash_included": False,
                "framebuffer_pixels_included": False,
                "debug_memory_included": False,
                "serial_payloads_included": False,
            },
            "session": {
                "id": session.id,
                "board_id": session.board.id,
                "state": session.state.value,
                "created_at": session.created_at.isoformat(),
                "expires_at": session.expires_at.isoformat(),
                "exit_code": session.exit_code,
                "generation": session.generation,
                "firmware": asdict(session.firmware),
                "replay": self._replay_dict(session),
            },
            "worker": {
                "sandbox": self.worker_sandbox_mode,
                "qmp_enabled": self._settings.worker_qmp_enabled,
                "debug_enabled": self._settings.worker_debug_enabled,
                "trace_enabled": self._settings.worker_trace_enabled,
            },
            "recording": {
                "events_dropped": session.events_dropped,
                "replayable_actions_dropped": session.replay_actions_dropped,
                "trace_events_recorded": session.trace_events_recorded,
                "trace_events_dropped": session.trace_events_dropped,
                "events": [event.public_dict() for event in session.events],
            },
            "serial": {
                "total_output_bytes": session.serial_output_bytes,
                "buffered_tail": serial_metadata(serial_tail),
            },
        }

    async def start_replay(self, session_id: str, speed: float) -> dict[str, object]:
        session = self.get(session_id)
        if session.state not in {SessionState.RUNNING, SessionState.PAUSED}:
            raise SessionTransitionError(f"cannot replay session in {session.state} state")
        if session.replay_task and not session.replay_task.done():
            raise SessionTransitionError("a replay is already running")
        if session.replay_actions_dropped:
            raise SessionTransitionError(
                "the replayable input recording exceeded its bound and is incomplete"
            )
        actions = tuple(session.replay_actions)
        if not actions:
            raise SessionTransitionError("the session has no replayable external input")
        replay_duration = actions[-1].offset_ms / 1000 / speed
        if replay_duration > self._settings.max_replay_duration_seconds:
            raise SessionTransitionError(
                "the requested replay duration exceeds the configured limit"
            )
        session.replay_status = "queued"
        session.replay_speed = speed
        session.replay_error = None
        session.accept_live_input = False
        self._record_event(
            session,
            "replay",
            "replay.queued",
            "user",
            {"action_count": len(actions), "speed": speed},
        )
        session.replay_task = asyncio.create_task(self._run_replay(session, actions, speed))
        return self._replay_dict(session)

    def replay_status(self, session_id: str) -> dict[str, object]:
        return self._replay_dict(self.get(session_id))

    async def _run_replay(
        self,
        session: SessionRecord,
        actions: tuple[ReplayAction, ...],
        speed: float,
    ) -> None:
        session.accept_live_input = False
        session.replay_status = "running"
        try:
            await self._terminate_worker(session)
            session.runtime_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            session.flash_path.write_bytes(session.initial_flash_image)
            session.flash_path.chmod(0o600)
            session.qmp_socket_path.unlink(missing_ok=True)
            session.gdb_socket_path.unlink(missing_ok=True)
            (session.runtime_directory / "framebuffer.ppm").unlink(missing_ok=True)
            session.serial_buffer.clear()
            session.serial_output_bytes = 0
            session.debug_breakpoints.clear()
            session.debug_stop_reason = None
            session.exit_code = None
            session.generation += 1
            session.generation_started_ns = time.monotonic_ns()
            session.replay_actions.clear()
            session.replay_actions_dropped = 0
            session.trace_events_recorded = 0
            session.trace_events_dropped = 0
            session.trace_event_counts.clear()
            session.trace_truncation_reported = False
            session.virtual_imu_state = None
            session.virtual_power_state = None
            session.state = SessionState.STARTING
            await self._launch(session)
            self._record_event(
                session,
                "replay",
                "replay.started",
                "service",
                {"action_count": len(actions), "speed": speed},
            )

            replay_started = time.monotonic()
            for action in actions:
                target = action.offset_ms / 1000 / speed
                delay = target - (time.monotonic() - replay_started)
                if delay > 0:
                    await asyncio.sleep(delay)
                replayed_action, public_data = await self._apply_replay_action(session, action)
                self._append_replay_action(session, replayed_action)
                control_event_types = {
                    "reset": "session.reset",
                    "power_off": "session.powered_off",
                    "power_on": "session.powered_on",
                }
                event_category = "control" if action.type in control_event_types else "input"
                event_type = control_event_types.get(action.type, f"input.{action.type}")
                self._record_event(
                    session,
                    event_category,
                    event_type,
                    "replay",
                    public_data,
                )

            session.replay_status = "completed"
            self._record_event(
                session,
                "replay",
                "replay.completed",
                "service",
                {"action_count": len(actions), "speed": speed},
            )
        except asyncio.CancelledError:
            session.replay_status = "cancelled"
            session.replay_error = None
            self._record_event(session, "replay", "replay.cancelled", "service")
            raise
        except Exception:
            session.replay_status = "failed"
            session.replay_error = "The worker could not complete the replay"
            if session.state is SessionState.STARTING:
                session.state = SessionState.FAILED
                shutil.rmtree(session.runtime_directory, ignore_errors=True)
                self._clear_private_session_data(session)
            self._record_event(session, "replay", "replay.failed", "service")
        finally:
            session.accept_live_input = True
            if session.replay_task is asyncio.current_task():
                session.replay_task = None

    async def _apply_replay_action(
        self, session: SessionRecord, action: ReplayAction
    ) -> tuple[ReplayAction, dict[str, object]]:
        offset_ms = self._offset_ms(session)
        if action.type == "serial":
            payload = action.payload
            if not isinstance(payload, bytes):
                raise RuntimeError("recorded serial input is invalid")
            process = session.process
            if session.state is not SessionState.RUNNING or not process or not process.stdin:
                raise RuntimeError("session serial input is not available")
            process.stdin.write(payload)
            await process.stdin.drain()
            return ReplayAction(offset_ms, "serial", payload), serial_metadata(payload)
        if action.type == "power_off":
            await self._power_off_worker(session)
            return ReplayAction(offset_ms, "power_off", None), {}
        if action.type == "power_on":
            await self._power_on_worker(session)
            return ReplayAction(offset_ms, "power_on", None), {}
        if action.type == "key":
            key, pressed = action.payload  # type: ignore[misc]
            arguments = qmp_key_event(session.board, key, pressed)
            command = "input-send-event"
            public_data = {"key": key, "pressed": pressed}
        elif action.type == "button":
            button, pressed = action.payload  # type: ignore[misc]
            arguments = qmp_button_event(session.board, button, pressed)
            command = "qom-set"
            public_data = {"button": button, "pressed": pressed}
        elif action.type == "imu":
            acceleration_g, angular_velocity_dps = action.payload  # type: ignore[misc]
            arguments = qmp_imu_sample(session.board, acceleration_g, angular_velocity_dps)
            command = "qom-set"
            public_data = {
                "acceleration_g": self._vector_dict(acceleration_g),
                "angular_velocity_dps": self._vector_dict(angular_velocity_dps),
            }
        elif action.type == "power":
            battery_mv, vin_mv, charging = action.payload  # type: ignore[misc]
            arguments = qmp_power_state(session.board, battery_mv, vin_mv, charging)
            command = "qom-set"
            public_data = {
                "battery_mv": battery_mv,
                "vin_mv": vin_mv,
                "charging": charging,
            }
        else:
            async with session.qmp_lock:
                await execute_qmp(session.qmp_socket_path, "system_reset")
            return ReplayAction(offset_ms, "reset", None), {}
        async with session.qmp_lock:
            await execute_qmp(session.qmp_socket_path, command, arguments)
        if action.type == "imu":
            session.virtual_imu_state = action.payload  # type: ignore[assignment]
        elif action.type == "power":
            session.virtual_power_state = action.payload  # type: ignore[assignment]
        return ReplayAction(offset_ms, action.type, action.payload), public_data

    async def _power_off_worker(self, session: SessionRecord) -> None:
        await self._terminate_worker(session)
        session.state = SessionState.POWERED_OFF
        session.exit_code = None
        self._publish(session, None)

    async def _power_on_worker(self, session: SessionRecord) -> None:
        session.qmp_socket_path.unlink(missing_ok=True)
        session.gdb_socket_path.unlink(missing_ok=True)
        (session.runtime_directory / "framebuffer.ppm").unlink(missing_ok=True)
        session.serial_buffer.clear()
        session.serial_output_bytes = 0
        session.debug_breakpoints.clear()
        session.debug_stop_reason = None
        session.exit_code = None
        session.trace_events_recorded = 0
        session.trace_events_dropped = 0
        session.trace_event_counts.clear()
        session.trace_truncation_reported = False
        session.state = SessionState.STARTING
        try:
            await self._launch(session)
            await self._restore_virtual_environment(session)
        except Exception:
            await self._terminate_worker(session)
            session.state = SessionState.FAILED
            self._clear_private_session_data(session)
            shutil.rmtree(session.runtime_directory, ignore_errors=True)
            self._publish(session, None)
            raise

    async def _restore_virtual_environment(self, session: SessionRecord) -> None:
        if not self._settings.worker_qmp_enabled:
            return
        async with session.qmp_lock:
            if session.virtual_imu_state is not None:
                acceleration_g, angular_velocity_dps = session.virtual_imu_state
                await execute_qmp(
                    session.qmp_socket_path,
                    "qom-set",
                    qmp_imu_sample(session.board, acceleration_g, angular_velocity_dps),
                )
            if session.virtual_power_state is not None:
                battery_mv, vin_mv, charging = session.virtual_power_state
                await execute_qmp(
                    session.qmp_socket_path,
                    "qom-set",
                    qmp_power_state(session.board, battery_mv, vin_mv, charging),
                )

    async def _terminate_worker(self, session: SessionRecord) -> None:
        await self._close_debugger(session)
        process = session.process
        reader_task = session.reader_task
        trace_reader_task = session.trace_reader_task
        session.process = None
        session.reader_task = None
        session.trace_reader_task = None
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()
        if reader_task and reader_task is not asyncio.current_task():
            await asyncio.gather(reader_task, return_exceptions=True)
        if trace_reader_task and trace_reader_task is not asyncio.current_task():
            await asyncio.gather(trace_reader_task, return_exceptions=True)
        session.exit_code = process.returncode if process else session.exit_code

    def _record_input(
        self,
        session: SessionRecord,
        action: ReplayAction,
        public_data: dict[str, object],
    ) -> None:
        self._append_replay_action(session, action)
        self._record_event(
            session,
            "input",
            f"input.{action.type}",
            "user",
            public_data,
        )

    @staticmethod
    def _clear_private_session_data(session: SessionRecord) -> None:
        session.initial_flash_image = b""
        session.replay_actions.clear()
        session.serial_buffer.clear()
        session.virtual_imu_state = None
        session.virtual_power_state = None

    def _append_replay_action(self, session: SessionRecord, action: ReplayAction) -> None:
        if len(session.replay_actions) >= self._settings.max_recording_events:
            session.replay_actions.popleft()
            session.replay_actions_dropped += 1
        session.replay_actions.append(action)

    def _record_event(
        self,
        session: SessionRecord,
        category: str,
        event_type: str,
        source: str,
        data: dict[str, object] | None = None,
    ) -> None:
        event = SessionEvent(
            sequence=session.next_event_sequence,
            generation=session.generation,
            offset_ms=self._offset_ms(session),
            category=category,  # type: ignore[arg-type]
            type=event_type,
            source=source,  # type: ignore[arg-type]
            data=data or {},
        )
        session.next_event_sequence += 1
        if len(session.events) >= self._settings.max_recording_events:
            session.events.popleft()
            session.events_dropped += 1
        session.events.append(event)

    @staticmethod
    def _offset_ms(session: SessionRecord) -> int:
        return max(0, (time.monotonic_ns() - session.generation_started_ns) // 1_000_000)

    @staticmethod
    def _vector_dict(vector: tuple[float, float, float]) -> dict[str, float]:
        return {"x": vector[0], "y": vector[1], "z": vector[2]}

    @staticmethod
    def _replay_dict(session: SessionRecord) -> dict[str, object]:
        return {
            "session_id": session.id,
            "generation": session.generation,
            "status": session.replay_status,
            "speed": session.replay_speed,
            "error": session.replay_error,
            "action_count": len(session.replay_actions),
            "actions_dropped": session.replay_actions_dropped,
        }

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
        worker_config = self._worker_config()
        worker_config.validate()
        if worker_config.sandbox_mode is WorkerSandboxMode.OCI_BROKER:
            try:
                process: WorkerProcess = await connect_broker_worker(
                    worker_config.broker_socket_path,
                    StartRequest(session_id=session.id, board_id=session.board.id),
                )
            except (BrokerUnavailableError, BrokerProtocolError) as error:
                raise WorkerUnavailableError("isolated worker broker launch failed") from error
        else:
            process = await self._launch_local_worker(worker_config, session)
        session.process = process
        session.reader_task = asyncio.create_task(self._read_serial(session, process))
        if process.stderr:
            session.trace_reader_task = asyncio.create_task(
                self._read_worker_trace(session, process.stderr)
            )
        try:
            if self._settings.worker_qmp_enabled:
                await self._wait_for_qmp_running(session, process)
            if (
                session.process is not process
                or process.returncode is not None
                or session.state is not SessionState.STARTING
            ):
                raise WorkerUnavailableError("simulator worker exited during startup")
        except (QmpError, WorkerUnavailableError) as error:
            logger.warning(
                "simulator worker startup readiness failed (cause=%s, worker_returncode=%s)",
                type(error).__name__,
                process.returncode,
            )
            await self._terminate_worker(session)
            raise WorkerUnavailableError(
                "simulator worker failed its startup readiness check"
            ) from error
        session.state = SessionState.RUNNING

    async def _wait_for_qmp_running(self, session: SessionRecord, process: WorkerProcess) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._settings.worker_startup_timeout_seconds
        last_unavailable: QmpUnavailableError | None = None
        while (remaining := deadline - loop.time()) > 0:
            if process.returncode is not None:
                raise WorkerUnavailableError("simulator worker exited during startup")
            try:
                status = await execute_qmp(
                    session.qmp_socket_path,
                    "query-status",
                    timeout_seconds=min(1.0, remaining),
                )
            except QmpUnavailableError as error:
                last_unavailable = error
            else:
                if (
                    isinstance(status, dict)
                    and status.get("running") is True
                    and status.get("status") == "running"
                ):
                    return
                if not (
                    isinstance(status, dict)
                    and status.get("running") is False
                    and status.get("status") == "prelaunch"
                ):
                    raise WorkerUnavailableError(
                        "simulator worker reported an invalid startup state"
                    )
            remaining = deadline - loop.time()
            if remaining > 0:
                await asyncio.sleep(min(0.05, remaining))
        raise WorkerUnavailableError(
            "simulator worker did not become ready before the startup deadline"
        ) from last_unavailable

    async def _launch_local_worker(
        self, worker_config: QemuWorkerConfig, session: SessionRecord
    ) -> asyncio.subprocess.Process:
        command = build_qemu_command(
            worker_config,
            session.board,
            session.flash_path,
            session.qmp_socket_path if self._settings.worker_qmp_enabled else None,
            (
                session.gdb_socket_path
                if self._settings.worker_debug_enabled and self._settings.worker_qmp_enabled
                else None
            ),
            trace_enabled=self._settings.worker_trace_enabled,
        )
        return await asyncio.create_subprocess_exec(
            *command,
            cwd=session.runtime_directory,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            start_new_session=True,
            preexec_fn=lambda: _limit_worker_resources(
                self._settings.worker_memory_limit_mib,
                self._settings.worker_cpu_limit_seconds,
            ),
        )

    async def _read_worker_trace(
        self, session: SessionRecord, stream: asyncio.StreamReader
    ) -> None:
        lines_read = 0
        while line := await stream.readline():
            lines_read += 1
            if lines_read % TRACE_READER_YIELD_LINES == 0:
                await asyncio.sleep(0)
            parsed = parse_worker_trace_line(line)
            if parsed is None:
                continue
            event_type, data = parsed
            trace_event = str(data["trace_event"])
            trace_event_count = session.trace_event_counts.get(trace_event, 0) + 1
            session.trace_event_counts[trace_event] = trace_event_count
            trace_event_limit = TRACE_EVENT_LIMITS[trace_event]
            if trace_event_count > trace_event_limit:
                if trace_event_count == trace_event_limit + 1:
                    self._record_event(
                        session,
                        "peripheral",
                        "peripheral.trace.sampled",
                        "worker",
                        {
                            "trace_event": trace_event,
                            "limit": trace_event_limit,
                        },
                    )
                session.trace_events_dropped += 1
                continue
            if session.trace_events_recorded >= self._settings.max_trace_events_per_generation:
                if not session.trace_truncation_reported:
                    self._record_event(
                        session,
                        "peripheral",
                        "peripheral.trace.truncated",
                        "worker",
                        {
                            "limit": self._settings.max_trace_events_per_generation,
                        },
                    )
                    session.trace_truncation_reported = True
                session.trace_events_dropped += 1
                continue
            session.trace_events_recorded += 1
            self._record_event(session, "peripheral", event_type, "worker", data)

    async def _read_serial(self, session: SessionRecord, process: WorkerProcess) -> None:
        if not process.stdout:
            return
        while chunk := await process.stdout.read(4096):
            if session.process is process:
                session.serial_output_bytes += len(chunk)
                session.serial_buffer.append(chunk)
                self._publish(session, chunk)
        exit_code = await process.wait()
        if session.process is not process:
            return
        trace_reader_task = session.trace_reader_task
        session.trace_reader_task = None
        if trace_reader_task and trace_reader_task is not asyncio.current_task():
            await asyncio.gather(trace_reader_task, return_exceptions=True)
        session.exit_code = exit_code
        await self._close_debugger(session)
        if session.state in {
            SessionState.STARTING,
            SessionState.RUNNING,
            SessionState.PAUSED,
        }:
            session.state = SessionState.STOPPED if session.exit_code == 0 else SessionState.FAILED
        self._record_event(
            session,
            "lifecycle",
            "worker.exited",
            "worker",
            {"exit_code": session.exit_code},
        )
        self._publish(session, None)
        self._clear_private_session_data(session)
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
                    if session.state in ACTIVE_SESSION_STATES and session.expires_at <= now
                ]
                for session_id in expired_ids:
                    await self.stop(session_id, expired=True)
        except asyncio.CancelledError:
            raise
