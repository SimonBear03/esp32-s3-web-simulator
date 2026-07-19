#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

import argparse
import asyncio
import tempfile
from pathlib import Path

from esp32_s3_simulator.boards import get_board_profile
from esp32_s3_simulator.qemu import DEFAULT_SANDBOX_READONLY_PATHS, WorkerSandboxMode
from esp32_s3_simulator.sessions import SessionManager, SessionRecord, SessionState
from esp32_s3_simulator.settings import Settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ESP32-S3 base firmware contract")
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--rom-directory", type=Path, required=True)
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--board-id", default="cardputer-adv")
    parser.add_argument(
        "--sandbox",
        choices=[mode.value for mode in WorkerSandboxMode],
        default=WorkerSandboxMode.DIRECT.value,
        help="native worker containment mode",
    )
    parser.add_argument(
        "--sandbox-executable",
        type=Path,
        default=Path("/usr/bin/bwrap"),
    )
    parser.add_argument(
        "--sandbox-readonly-path",
        action="append",
        dest="sandbox_readonly_paths",
        type=Path,
        help="additional read-only path set (repeat; replaces the default set)",
    )
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
            worker_debug_enabled=args.qmp,
            worker_sandbox_mode=WorkerSandboxMode(args.sandbox),
            worker_sandbox_executable=args.sandbox_executable.resolve(),
            worker_sandbox_readonly_paths=(
                tuple(path.absolute() for path in args.sandbox_readonly_paths)
                if args.sandbox_readonly_paths
                else DEFAULT_SANDBOX_READONLY_PATHS
            ),
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
                await wait_for_text(
                    session,
                    "SIM:LEDC channel=7 pin=38 frequency=256 duty=110 configured=1",
                )
            else:
                await wait_for_text(session, "SIM:PSRAM bytes=8388608 test=pass")
                await wait_for_text(
                    session, "SIM:BUTTONS a_gpio=11 b_gpio=12 active=low"
                )
                await wait_for_text(
                    session, "SIM:BMI270 address=0x68 chip_id=0x24 ready=1"
                )
                await wait_for_text(
                    session, "SIM:M5PM1 address=0x6e device_id=0x51 ready=1"
                )
                await wait_for_text(
                    session, "SIM:IMU_RAW ax=0 ay=0 az=4096 gx=0 gy=0 gz=0"
                )
                await wait_for_text(
                    session,
                    "SIM:POWER battery_mv=3900 vin_mv=5000 source=0 charging=1",
                )
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
                registers = await manager.debug_registers(session.id)
                pc = registers.get("pc")
                if not isinstance(pc, int):
                    raise RuntimeError("debugger did not expose the Xtensa PC register")
                instruction = await manager.debug_read_memory(session.id, pc, 4)
                if len(instruction) != 4:
                    raise RuntimeError("debugger returned a short instruction read")
                await manager.debug_set_breakpoint(session.id, pc, True)
                await manager.debug_set_breakpoint(session.id, pc, False)
                stop_reason = await manager.debug_step(session.id)
                if not stop_reason.startswith(("S", "T")):
                    raise RuntimeError("debugger single-step did not stop the CPU")
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
                else:
                    await manager.send_button(session.id, "a", True)
                    await wait_for_text(session, "SIM:BUTTON id=a pressed=1")
                    await manager.send_button(session.id, "a", False)
                    await wait_for_text(session, "SIM:BUTTON id=a pressed=0")
                    await manager.send_button(session.id, "b", True)
                    await wait_for_text(session, "SIM:BUTTON id=b pressed=1")
                    await manager.send_button(session.id, "b", False)
                    await wait_for_text(session, "SIM:BUTTON id=b pressed=0")

                    await manager.set_imu_sample(
                        session.id, (1.0, 0.0, 0.0), (0.0, 0.0, 250.0)
                    )
                    await wait_for_text(
                        session,
                        "SIM:IMU_RAW ax=4096 ay=0 az=0 gx=0 gy=0 gz=4096",
                    )
                    await manager.set_power_state(
                        session.id, battery_mv=3700, vin_mv=0, charging=False
                    )
                    await wait_for_text(
                        session,
                        "SIM:POWER battery_mv=3700 vin_mv=0 source=2 charging=0",
                    )

            await manager.write_serial(session.id, b"ping\n")
            await wait_for_text(session, "SIM:PONG")

            expected_boot_count = 1
            if args.qmp:
                heartbeat_count = serial_text(session).count("SIM:HEARTBEAT")
                await manager.reset(session.id)
                expected_boot_count += 1
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
