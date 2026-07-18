#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

import argparse
import asyncio
import tempfile
from pathlib import Path

from esp32_s3_simulator.boards import CARDPUTER_ADV
from esp32_s3_simulator.sessions import SessionManager, SessionRecord, SessionState
from esp32_s3_simulator.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ESP32-S3 base firmware contract")
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--rom-directory", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument(
        "--qmp",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="enable the private QMP Unix socket (disable only in restricted test sandboxes)",
    )
    return parser.parse_args()


def serial_text(session: SessionRecord) -> str:
    return b"".join(session.serial_buffer).decode("utf-8", "replace")


async def wait_for_text(
    session: SessionRecord, expected: str, *, count: int = 1, timeout: float = 8
) -> str:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        output = serial_text(session)
        if output.count(expected) >= count:
            return output
        if session.state is not SessionState.RUNNING:
            raise RuntimeError(
                f"worker stopped before {expected!r}; state={session.state}\n{output}"
            )
        await asyncio.sleep(0.05)
    raise TimeoutError(f"timed out waiting for {expected!r}\n{serial_text(session)}")


async def run(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory(prefix="esp32-base-conformance-") as runtime_root:
        settings = Settings(
            runtime_root=Path(runtime_root),
            qemu_executable=args.qemu.resolve(),
            rom_directory=args.rom_directory.resolve(),
            native_workers_enabled=True,
            worker_qmp_enabled=args.qmp,
            session_ttl_seconds=30,
            worker_memory_limit_mib=1536,
            worker_cpu_limit_seconds=20,
        )
        manager = SessionManager(settings)
        await manager.start()
        try:
            session = await manager.create(CARDPUTER_ADV, args.firmware.read_bytes())
            await wait_for_text(session, "SIM:READY")
            await wait_for_text(session, "SIM:HEARTBEAT", count=3)

            await manager.write_serial(session.id, b"ping\n")
            await wait_for_text(session, "SIM:PONG")

            await manager.write_serial(session.id, b"reset\n")
            await wait_for_text(session, "SIM:BOOT", count=2)
            output = await wait_for_text(session, "SIM:NVS boot_count=2")
            await wait_for_text(session, "SIM:HEARTBEAT", count=4)

            print(output)
            print("BASE CONFORMANCE PASSED")
            await manager.stop(session.id)
            if session.runtime_directory.exists():
                raise RuntimeError("session runtime directory was not removed")
        finally:
            await manager.close()


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
