# SPDX-License-Identifier: GPL-2.0-only

import argparse
import asyncio
import json
import logging
import os
import re
import signal
import socket
import stat
import struct
from contextlib import suppress
from dataclasses import dataclass

from .broker_protocol import (
    MAX_CONTROL_PAYLOAD,
    MAX_STREAM_CHUNK,
    BrokerProtocolError,
    ErrorMessage,
    ExitMessage,
    FrameKind,
    FrameWriter,
    StartRequest,
    read_frame,
)
from .oci import OciBrokerSettings, OciPolicyError

LOGGER = logging.getLogger("esp32_s3_simulator.worker_broker")
_PEER_CREDENTIALS = struct.Struct("3i")
_MINIMAL_ENVIRONMENT = {
    "HOME": "/nonexistent",
    "LANG": "C.UTF-8",
    "PATH": "/usr/bin:/bin",
}


@dataclass(slots=True)
class _OutputBudget:
    remaining: int
    exceeded: asyncio.Event
    lock: asyncio.Lock

    @classmethod
    def create(cls, limit_bytes: int) -> "_OutputBudget":
        return cls(limit_bytes, asyncio.Event(), asyncio.Lock())

    async def consume(self, size: int) -> bool:
        async with self.lock:
            if size > self.remaining:
                self.exceeded.set()
                return False
            self.remaining -= size
            return True


class OciWorkerBroker:
    def __init__(
        self,
        settings: OciBrokerSettings,
        *,
        output_limit_bytes: int = 32 * 1024 * 1024,
    ) -> None:
        self._settings = settings
        self._output_limit_bytes = output_limit_bytes
        self._server: asyncio.AbstractServer | None = None
        self._active: set[str] = set()
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._lock = asyncio.Lock()
        self._reconcile_task: asyncio.Task[None] | None = None
        self._runtime_healthy = False

    @property
    def active_count(self) -> int:
        return len(self._active)

    async def start(self, *, verify_runtime: bool = True) -> None:
        self._settings.validate()
        self._validate_socket_parent()
        if verify_runtime:
            await self.verify_runtime()
            await self.reconcile_managed_containers()
        self._runtime_healthy = True
        self._remove_stale_socket()
        self._server = await asyncio.start_unix_server(
            self._handle_connection,
            path=self._settings.socket_path,
            start_serving=False,
        )
        os.chown(self._settings.socket_path, -1, self._settings.shared_group_gid)
        self._settings.socket_path.chmod(0o660)
        await self._server.start_serving()
        if verify_runtime:
            self._reconcile_task = asyncio.create_task(self._reconcile_loop())

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        if self._reconcile_task is not None:
            self._reconcile_task.cancel()
            await asyncio.gather(self._reconcile_task, return_exceptions=True)
            self._reconcile_task = None
        self._runtime_healthy = False
        async with self._lock:
            active = tuple(self._active)
            processes = dict(self._processes)
        await asyncio.gather(
            *(self._force_cleanup(session_id, processes.get(session_id)) for session_id in active),
            return_exceptions=True,
        )
        self._remove_stale_socket()

    async def serve_forever(self) -> None:
        if self._server is None:
            raise RuntimeError("worker broker has not started")
        await self._server.serve_forever()

    def _validate_socket_parent(self) -> None:
        parent = self._settings.socket_path.parent
        try:
            parent_stat = parent.lstat()
        except FileNotFoundError as error:
            raise OciPolicyError("broker socket parent is unavailable") from error
        if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
            raise OciPolicyError("broker socket parent must be a non-symlink directory")
        if parent_stat.st_gid != self._settings.shared_group_gid:
            raise OciPolicyError("broker socket parent has an unexpected group")
        if stat.S_IMODE(parent_stat.st_mode) & 0o007:
            raise OciPolicyError("broker socket parent must not be accessible to other users")

    def _remove_stale_socket(self) -> None:
        try:
            socket_stat = self._settings.socket_path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(socket_stat.st_mode) or socket_stat.st_uid != os.getuid():
            raise OciPolicyError("refusing to replace an unowned broker socket path")
        self._settings.socket_path.unlink()

    async def verify_runtime(self) -> None:
        security_output = await self._docker_output(
            "info", "--format", "{{json .SecurityOptions}}"
        )
        try:
            security_options = json.loads(security_output)
        except json.JSONDecodeError as error:
            raise OciPolicyError("Docker returned invalid security metadata") from error
        if not isinstance(security_options, list) or not all(
            isinstance(item, str) for item in security_options
        ):
            raise OciPolicyError("Docker returned invalid security options")
        if "name=rootless" not in security_options:
            raise OciPolicyError("the configured Docker daemon is not rootless")
        if not any(item.startswith("name=seccomp") for item in security_options):
            raise OciPolicyError("the configured Docker daemon does not report seccomp")
        cgroup_version = await self._docker_output(
            "info", "--format", "{{.CgroupVersion}}"
        )
        if cgroup_version != "2":
            raise OciPolicyError("the rootless Docker daemon must use cgroup v2")
        image_id = await self._docker_output(
            "image", "inspect", "--format", "{{.Id}}", self._settings.image_reference
        )
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise OciPolicyError("the pinned worker image is unavailable")

    async def reconcile_managed_containers(self, *, preserve_active: bool = False) -> None:
        output = await self._docker_output(*self._settings.list_managed_command()[3:])
        container_names = [line.strip() for line in output.splitlines() if line.strip()]
        async with self._lock:
            active = set(self._active) if preserve_active else set()
        for container_name in container_names:
            session_id = self._settings.session_id_from_container_name(container_name)
            if session_id in active:
                continue
            if not await self._docker_control("rm", session_id):
                raise OciPolicyError("managed container reconciliation failed")

    async def _reconcile_loop(self) -> None:
        while True:
            await asyncio.sleep(30)
            try:
                await self.verify_runtime()
                await self.reconcile_managed_containers(preserve_active=True)
                self._runtime_healthy = True
            except OciPolicyError:
                self._runtime_healthy = False
                LOGGER.error("rootless worker runtime health check failed")

    async def _docker_output(self, *arguments: str, timeout_seconds: float = 10.0) -> str:
        process = await asyncio.create_subprocess_exec(
            *self._settings.docker_prefix,
            *arguments,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=_MINIMAL_ENVIRONMENT,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout_seconds)
        except TimeoutError as error:
            process.kill()
            await process.wait()
            raise OciPolicyError("Docker runtime verification timed out") from error
        if process.returncode != 0 or len(stdout) > 64 * 1024:
            raise OciPolicyError("Docker runtime verification failed")
        try:
            return stdout.decode("utf-8").strip()
        except UnicodeDecodeError as error:
            raise OciPolicyError("Docker runtime verification returned invalid text") from error

    def _peer_uid(self, writer: asyncio.StreamWriter) -> int | None:
        transport_socket = writer.get_extra_info("socket")
        if transport_socket is None:
            return None
        try:
            credentials = transport_socket.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, _PEER_CREDENTIALS.size
            )
        except OSError:
            return None
        _, uid, _ = _PEER_CREDENTIALS.unpack(credentials)
        return uid

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if self._peer_uid(writer) != self._settings.allowed_core_uid:
            writer.close()
            await writer.wait_closed()
            return
        frames = FrameWriter(writer)
        try:
            first = await asyncio.wait_for(
                read_frame(reader, max_payload=MAX_CONTROL_PAYLOAD), timeout=3.0
            )
            if first.kind is FrameKind.PING and not first.payload:
                if self._runtime_healthy:
                    await frames.send(FrameKind.PONG)
                else:
                    await self._safe_error(frames, "runtime", "Worker runtime is unavailable")
                return
            if first.kind is not FrameKind.START:
                raise BrokerProtocolError("first broker frame must be ping or start")
            request = StartRequest.from_payload(first.payload)
            if not self._runtime_healthy:
                await self._safe_error(frames, "runtime", "Worker runtime is unavailable")
                return
            await self._run_worker(request, reader, frames)
        except TimeoutError:
            await self._safe_error(frames, "timeout", "Broker request timed out")
        except BrokerProtocolError:
            await self._safe_error(frames, "protocol", "Broker request was invalid")
        except OciPolicyError:
            await self._safe_error(frames, "policy", "Worker policy validation failed")
        except (ConnectionError, BrokenPipeError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def _claim(self, session_id: str) -> bool:
        async with self._lock:
            if (
                not self._runtime_healthy
                or session_id in self._active
                or len(self._active) >= self._settings.max_workers
            ):
                return False
            self._active.add(session_id)
            return True

    async def _release(self, session_id: str) -> None:
        async with self._lock:
            self._active.discard(session_id)
            self._processes.pop(session_id, None)

    async def _run_worker(
        self,
        request: StartRequest,
        reader: asyncio.StreamReader,
        frames: FrameWriter,
    ) -> None:
        if not await self._claim(request.session_id):
            await self._safe_error(frames, "capacity", "All isolated workers are busy")
            return
        process: asyncio.subprocess.Process | None = None
        try:
            command = self._settings.build_worker_command(request)
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=_MINIMAL_ENVIRONMENT,
                )
            except OSError:
                await self._safe_error(frames, "launch", "Isolated worker could not start")
                return
            async with self._lock:
                self._processes[request.session_id] = process
            await frames.send(FrameKind.STARTED)
            budget = _OutputBudget.create(self._output_limit_bytes)
            stdout_task = asyncio.create_task(
                self._pump_output(process.stdout, frames, FrameKind.STDOUT, budget)
            )
            stderr_task = asyncio.create_task(
                self._pump_output(process.stderr, frames, FrameKind.STDERR, budget)
            )
            control_task = asyncio.create_task(
                self._relay_control(reader, process, request.session_id)
            )
            wait_task = asyncio.create_task(process.wait())
            wall_task = asyncio.create_task(asyncio.sleep(self._settings.wall_time_seconds))
            budget_task = asyncio.create_task(budget.exceeded.wait())
            done, _ = await asyncio.wait(
                {control_task, wait_task, wall_task, budget_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if wait_task not in done:
                reason = "disconnect"
                if wall_task in done:
                    reason = "wall-time"
                elif budget_task in done:
                    reason = "output-limit"
                LOGGER.warning(
                    "terminating isolated worker reason=%s session=%s",
                    reason,
                    request.session_id,
                )
                await self._docker_control("kill", request.session_id)
                if process.returncode is None:
                    process.kill()
                await process.wait()
            returncode = process.returncode if process.returncode is not None else 125
            returncode = max(-255, min(255, returncode))
            for task in (control_task, wall_task, budget_task):
                task.cancel()
            await asyncio.gather(control_task, wall_task, budget_task, return_exceptions=True)
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
            await self._safe_send(frames, FrameKind.EXIT, ExitMessage(returncode).to_payload())
        finally:
            if process is not None and process.returncode is None:
                await self._docker_control("kill", request.session_id)
                process.kill()
                await process.wait()
            await self._docker_control("rm", request.session_id)
            await self._release(request.session_id)

    async def _force_cleanup(
        self,
        session_id: str,
        process: asyncio.subprocess.Process | None,
    ) -> None:
        await self._docker_control("kill", session_id)
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        await self._docker_control("rm", session_id)

    async def _relay_control(
        self,
        reader: asyncio.StreamReader,
        process: asyncio.subprocess.Process,
        session_id: str,
    ) -> None:
        while process.returncode is None:
            frame = await read_frame(reader, max_payload=MAX_STREAM_CHUNK)
            if frame.kind is FrameKind.STDIN:
                if process.stdin is None:
                    raise BrokerProtocolError("worker stdin is unavailable")
                process.stdin.write(frame.payload)
                await process.stdin.drain()
            elif frame.kind is FrameKind.TERMINATE and not frame.payload:
                await self._docker_control("stop", session_id)
            elif frame.kind is FrameKind.KILL and not frame.payload:
                await self._docker_control("kill", session_id)
            else:
                raise BrokerProtocolError("worker control frame is invalid")

    async def _pump_output(
        self,
        stream: asyncio.StreamReader | None,
        frames: FrameWriter,
        kind: FrameKind,
        budget: _OutputBudget,
    ) -> None:
        if stream is None:
            return
        while chunk := await stream.read(MAX_STREAM_CHUNK):
            if not await budget.consume(len(chunk)):
                return
            await frames.send(kind, chunk)

    async def _docker_control(
        self,
        action: str,
        identifier: str,
    ) -> bool:
        command = self._settings.control_command(action, identifier)
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                env=_MINIMAL_ENVIRONMENT,
            )
            try:
                return await asyncio.wait_for(process.wait(), timeout=10.0) == 0
            except TimeoutError:
                process.kill()
                await process.wait()
                return False
        except OSError:
            return False

    async def _safe_error(
        self, frames: FrameWriter, code: str, message: str
    ) -> None:
        await self._safe_send(frames, FrameKind.ERROR, ErrorMessage(code, message).to_payload())

    @staticmethod
    async def _safe_send(frames: FrameWriter, kind: FrameKind, payload: bytes) -> None:
        with suppress(BrokerProtocolError, ConnectionError, BrokenPipeError):
            await frames.send(kind, payload)


async def _run(settings: OciBrokerSettings) -> None:
    broker = OciWorkerBroker(settings)
    await broker.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    LOGGER.info("isolated worker broker ready")
    await stop.wait()
    await broker.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the rootless OCI worker broker")
    parser.add_argument("--log-level", default="INFO")
    arguments = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, arguments.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(_run(OciBrokerSettings.from_environment()))


if __name__ == "__main__":
    main()
