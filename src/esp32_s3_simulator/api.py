# SPDX-License-Identifier: GPL-2.0-only

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from . import __version__
from .boards import BOARD_PROFILES, get_board_profile
from .firmware import FirmwareValidationError
from .gdb import GdbRemoteError
from .inputs import BoardInputError
from .qmp import QmpError
from .sessions import (
    MAX_DEBUG_BREAKPOINTS,
    SessionCapacityError,
    SessionManager,
    SessionNotFoundError,
    SessionTransitionError,
    WorkerUnavailableError,
)
from .settings import Settings


class KeyInputMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["key"]
    key: str
    pressed: bool
    sequence: int | str | None = None


class ButtonInputMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["button"]
    button: Literal["a", "b"]
    pressed: bool
    sequence: int | str | None = None


class Vector3Message(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


class ImuInputMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["imu"]
    acceleration_g: Vector3Message
    angular_velocity_dps: Vector3Message
    sequence: int | str | None = None


class PowerInputMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["power"]
    battery_mv: int
    vin_mv: int
    charging: bool
    sequence: int | str | None = None


InputMessage = Annotated[
    KeyInputMessage | ButtonInputMessage | ImuInputMessage | PowerInputMessage,
    Field(discriminator="type"),
]
INPUT_MESSAGE_ADAPTER = TypeAdapter(InputMessage)


class SessionControlMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["pause", "resume", "reset"]


class SessionReplayMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speed: Annotated[float, Field(ge=0.25, le=4.0)] = 1.0


class DebugMemoryReadMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: Annotated[int, Field(ge=0, le=0xFFFFFFFF)]
    length: Annotated[int, Field(ge=1, le=4096)]


class DebugBreakpointMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: Annotated[int, Field(ge=0, le=0xFFFFFFFF)]
    enabled: bool


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings.from_environment()
    manager = SessionManager(resolved_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await manager.start()
        yield
        await manager.close()

    app = FastAPI(
        title="ESP32-S3 Web Simulator API",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.session_manager = manager

    @app.get("/health/live")
    async def live() -> dict[str, object]:
        return {"status": "ok", "version": __version__}

    @app.get("/health/ready")
    async def ready() -> dict[str, object]:
        worker_ready = await manager.worker_is_ready()
        return {
            "status": "ready" if worker_ready else "degraded",
            "native_worker": worker_ready,
            "worker_sandbox": manager.worker_sandbox_mode,
        }

    @app.get("/v1/boards")
    async def list_boards() -> list[dict[str, object]]:
        return [profile.as_public_dict() for profile in BOARD_PROFILES.values()]

    @app.post("/v1/sessions", status_code=201)
    async def create_session(
        board_id: Annotated[str, Form()],
        firmware: Annotated[UploadFile, File()],
    ) -> dict[str, object]:
        try:
            board = get_board_profile(board_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        upload = await firmware.read(board.flash_size_bytes + 1)
        try:
            session = await manager.create(board, upload)
        except FirmwareValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except WorkerUnavailableError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except SessionCapacityError as error:
            raise HTTPException(status_code=429, detail=str(error)) from error
        return session.public_dict()

    @app.get("/v1/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, object]:
        try:
            return (await manager.refresh_state(session_id)).public_dict()
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error
        except QmpError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.delete("/v1/sessions/{session_id}")
    async def stop_session(session_id: str) -> dict[str, object]:
        try:
            return (await manager.stop(session_id)).public_dict()
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error

    @app.post("/v1/sessions/{session_id}/control")
    async def control_session(
        session_id: str, control: SessionControlMessage
    ) -> dict[str, object]:
        try:
            if control.action == "pause":
                session = await manager.pause(session_id)
            elif control.action == "resume":
                session = await manager.resume(session_id)
            else:
                session = await manager.reset(session_id)
            return session.public_dict()
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error
        except SessionTransitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (GdbRemoteError, QmpError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/v1/sessions/{session_id}/events")
    async def session_events(
        session_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1)] = 200,
    ) -> dict[str, object]:
        try:
            return manager.list_events(session_id, after=after, limit=limit)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error

    @app.get("/v1/sessions/{session_id}/diagnostics")
    async def session_diagnostics(session_id: str) -> JSONResponse:
        try:
            payload = manager.diagnostics(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error
        return JSONResponse(
            payload,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="esp32-s3-simulator-{session_id}.json"'
                ),
                "Cache-Control": "no-store",
            },
        )

    @app.get("/v1/sessions/{session_id}/replay")
    async def session_replay_status(session_id: str) -> dict[str, object]:
        try:
            return manager.replay_status(session_id)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error

    @app.post("/v1/sessions/{session_id}/replay", status_code=202)
    async def replay_session(
        session_id: str, request: SessionReplayMessage
    ) -> dict[str, object]:
        try:
            return await manager.start_replay(session_id, request.speed)
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error
        except SessionTransitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/v1/sessions/{session_id}/debug/status")
    async def debug_status(session_id: str) -> dict[str, object]:
        try:
            session = await manager.refresh_state(session_id)
            return {
                "state": session.state,
                "stop_reason": session.debug_stop_reason,
                "enabled": (
                    resolved_settings.worker_debug_enabled
                    and resolved_settings.worker_qmp_enabled
                ),
                "capabilities": {
                    "register_read": True,
                    "memory_read_max_bytes": 4096,
                    "hardware_breakpoints_max": MAX_DEBUG_BREAKPOINTS,
                    "single_step": True,
                    "memory_write": False,
                    "register_write": False,
                    "raw_gdb": False,
                },
            }
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error
        except QmpError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/v1/sessions/{session_id}/debug/registers")
    async def debug_registers(session_id: str) -> dict[str, object]:
        try:
            return {"registers": await manager.debug_registers(session_id)}
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error
        except SessionTransitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (GdbRemoteError, QmpError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post("/v1/sessions/{session_id}/debug/memory")
    async def debug_memory(session_id: str, request: DebugMemoryReadMessage) -> dict[str, object]:
        try:
            data = await manager.debug_read_memory(session_id, request.address, request.length)
            return {
                "address": request.address,
                "length": len(data),
                "data_hex": data.hex(),
            }
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error
        except SessionTransitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (GdbRemoteError, QmpError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post("/v1/sessions/{session_id}/debug/breakpoint")
    async def debug_breakpoint(
        session_id: str, request: DebugBreakpointMessage
    ) -> dict[str, object]:
        try:
            await manager.debug_set_breakpoint(session_id, request.address, request.enabled)
            return {"address": request.address, "enabled": request.enabled}
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error
        except SessionTransitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (GdbRemoteError, QmpError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post("/v1/sessions/{session_id}/debug/step")
    async def debug_step(session_id: str) -> dict[str, object]:
        try:
            return {"stop_reason": await manager.debug_step(session_id)}
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error
        except SessionTransitionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (GdbRemoteError, QmpError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.websocket("/v1/sessions/{session_id}/serial")
    async def session_serial(websocket: WebSocket, session_id: str) -> None:
        try:
            manager.get(session_id)
        except SessionNotFoundError:
            await websocket.close(code=4404, reason="simulation session not found")
            return

        await websocket.accept()

        async def send_serial() -> None:
            async for chunk in manager.subscribe_serial(session_id):
                await websocket.send_bytes(chunk)

        async def receive_serial() -> None:
            while True:
                payload = await websocket.receive_bytes()
                await manager.write_serial(session_id, payload)

        tasks = {asyncio.create_task(send_serial()), asyncio.create_task(receive_serial())}
        try:
            _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        except WebSocketDisconnect:
            pass

    @app.websocket("/v1/sessions/{session_id}/input")
    async def session_input(websocket: WebSocket, session_id: str) -> None:
        try:
            manager.get(session_id)
        except SessionNotFoundError:
            await websocket.close(code=4404, reason="simulation session not found")
            return

        await websocket.accept()
        try:
            while True:
                payload = await websocket.receive_text()
                try:
                    event = INPUT_MESSAGE_ADAPTER.validate_json(payload)
                    if isinstance(event, KeyInputMessage):
                        await manager.send_key(session_id, event.key, event.pressed)
                    elif isinstance(event, ButtonInputMessage):
                        await manager.send_button(
                            session_id, event.button, event.pressed
                        )
                    elif isinstance(event, ImuInputMessage):
                        await manager.set_imu_sample(
                            session_id,
                            event.acceleration_g.as_tuple(),
                            event.angular_velocity_dps.as_tuple(),
                        )
                    else:
                        await manager.set_power_state(
                            session_id,
                            event.battery_mv,
                            event.vin_mv,
                            event.charging,
                        )
                    await websocket.send_json({"type": "ack", "sequence": event.sequence})
                except ValidationError as error:
                    await websocket.send_json(
                        {"type": "error", "code": "invalid-event", "detail": str(error)}
                    )
                except BoardInputError as error:
                    await websocket.send_json(
                        {"type": "error", "code": "unsupported-input", "detail": str(error)}
                    )
                except (QmpError, RuntimeError) as error:
                    await websocket.send_json(
                        {"type": "error", "code": "worker-unavailable", "detail": str(error)}
                    )
        except WebSocketDisconnect:
            pass

    @app.websocket("/v1/sessions/{session_id}/framebuffer")
    async def session_framebuffer(websocket: WebSocket, session_id: str) -> None:
        try:
            manager.get(session_id)
        except SessionNotFoundError:
            await websocket.close(code=4404, reason="simulation session not found")
            return

        await websocket.accept()
        try:
            async for packet in manager.subscribe_framebuffer(session_id):
                await websocket.send_bytes(packet)
        except WebSocketDisconnect:
            pass
        except (QmpError, RuntimeError):
            await websocket.close(code=1011, reason="framebuffer worker unavailable")

    return app


app = create_app()
