# SPDX-License-Identifier: GPL-2.0-only

import asyncio
from typing import Protocol


class WorkerStdin(Protocol):
    def write(self, payload: bytes) -> None: ...

    async def drain(self) -> None: ...


class WorkerProcess(Protocol):
    stdin: WorkerStdin | None
    stdout: asyncio.StreamReader | None
    stderr: asyncio.StreamReader | None

    @property
    def returncode(self) -> int | None: ...

    async def wait(self) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...
