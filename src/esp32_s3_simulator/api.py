# SPDX-License-Identifier: GPL-2.0-only

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from . import __version__
from .boards import BOARD_PROFILES, get_board_profile
from .firmware import FirmwareValidationError
from .sessions import (
    SessionCapacityError,
    SessionManager,
    SessionNotFoundError,
    WorkerUnavailableError,
)
from .settings import Settings


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
        return {
            "status": "ready" if manager.worker_ready else "degraded",
            "native_worker": manager.worker_ready,
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
            return manager.get(session_id).public_dict()
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error

    @app.delete("/v1/sessions/{session_id}")
    async def stop_session(session_id: str) -> dict[str, object]:
        try:
            return (await manager.stop(session_id)).public_dict()
        except SessionNotFoundError as error:
            raise HTTPException(status_code=404, detail="simulation session not found") from error

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

    return app


app = create_app()
