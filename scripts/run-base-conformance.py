#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

import argparse
import asyncio
import tempfile
from pathlib import Path

from esp32_s3_simulator.boards import get_board_profile
from esp32_s3_simulator.sessions import SessionManager, SessionRecord, SessionState
from esp32_s3_simulator.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ESP32-S3 base firmware contract")
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--rom-directory", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--board-id", default="cardputer-adv")
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
    board = get_board_profile(args.board_id)
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
            session = await manager.create(board, args.firmware.read_bytes())
            if board.id == "cardputer-adv":
                await wait_for_text(session, "SIM:TCA8418 address=0x34 cfg=0x01")
                await wait_for_text(session, "SIM:TCA8418_IRQ pin=11 mode=change")
            else:
                await wait_for_text(session, "SIM:PSRAM bytes=8388608 test=pass")
            await wait_for_text(
                session,
                f"SIM:DISPLAY controller=st7789 width={board.display.width} "
                f"height={board.display.height} pattern=red-blue",
            )
            await wait_for_text(session, f"SIM:BOOT version=1 profile={board.id}")
            await wait_for_text(
                session, "SIM:NVS boot_count=1 write_bytes=4 readback=1"
            )
            await wait_for_text(session, "SIM:READY")
            await wait_for_text(session, "SIM:HEARTBEAT", count=3)

            if args.qmp:
                await manager.pause(session.id)
                if session.state is not SessionState.PAUSED:
                    raise RuntimeError("session did not enter paused state")
                await asyncio.sleep(0.1)
                paused_heartbeat_count = serial_text(session).count("SIM:HEARTBEAT")
                await asyncio.sleep(0.65)
                if serial_text(session).count("SIM:HEARTBEAT") != paused_heartbeat_count:
                    raise RuntimeError("firmware continued running while session was paused")

                frame = await manager.capture_framebuffer(session.id)
                expected_size = (board.display.width, board.display.height)
                if (frame.width, frame.height) != expected_size:
                    raise RuntimeError(
                        f"unexpected {board.id} framebuffer size: {frame.width}x{frame.height}"
                    )
                if frame.pixel(0, 0) != (255, 0, 0):
                    raise RuntimeError(f"{board.id} framebuffer top half is not red")
                red_row = board.display.height // 2 - 1
                blue_row = board.display.height // 2
                if frame.pixel(board.display.width - 1, red_row) != (255, 0, 0):
                    raise RuntimeError(f"{board.id} framebuffer red boundary is incorrect")
                if frame.pixel(0, blue_row) != (0, 0, 255):
                    raise RuntimeError(f"{board.id} framebuffer blue boundary is incorrect")
                if frame.pixel(board.display.width - 1, board.display.height - 1) != (
                    0,
                    0,
                    255,
                ):
                    raise RuntimeError(f"{board.id} framebuffer bottom half is not blue")

                await manager.resume(session.id)
                if session.state is not SessionState.RUNNING:
                    raise RuntimeError("session did not return to running state")
                await wait_for_text(
                    session, "SIM:HEARTBEAT", count=paused_heartbeat_count + 1
                )

                if board.id == "cardputer-adv":
                    await manager.send_key(session.id, "a", True)
                    await manager.send_key(session.id, "a", False)
                    await wait_for_text(session, "SIM:KEY raw=0x8d")
                    await wait_for_text(session, "SIM:KEY raw=0x0d")

            await manager.write_serial(session.id, b"ping\n")
            await wait_for_text(session, "SIM:PONG")

            expected_boot_count = 1
            if args.qmp:
                heartbeat_count = serial_text(session).count("SIM:HEARTBEAT")
                await manager.reset(session.id)
                expected_boot_count += 1
                await wait_for_text(session, "SIM:BOOT", count=expected_boot_count)
                await wait_for_text(
                    session,
                    f"SIM:NVS boot_count={expected_boot_count} "
                    f"write_bytes=4 readback={expected_boot_count}",
                )
                await wait_for_text(
                    session, "SIM:HEARTBEAT", count=heartbeat_count + 1
                )

            heartbeat_count = serial_text(session).count("SIM:HEARTBEAT")
            await manager.write_serial(session.id, b"reset\n")
            expected_boot_count += 1
            await wait_for_text(session, "SIM:BOOT", count=expected_boot_count)
            output = await wait_for_text(
                session,
                f"SIM:NVS boot_count={expected_boot_count} "
                f"write_bytes=4 readback={expected_boot_count}",
            )
            await wait_for_text(
                session, "SIM:HEARTBEAT", count=heartbeat_count + 1
            )

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
