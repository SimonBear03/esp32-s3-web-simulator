# SPDX-License-Identifier: GPL-2.0-only

import asyncio
import os
from pathlib import Path

import pytest

from esp32_s3_simulator.boards import CARDPUTER_ADV
from esp32_s3_simulator.broker_protocol import StartRequest, connect_broker_worker, probe_broker
from esp32_s3_simulator.oci import OciBrokerSettings, OciPolicyError
from esp32_s3_simulator.qemu import WorkerSandboxMode
from esp32_s3_simulator.sessions import SessionManager
from esp32_s3_simulator.settings import Settings
from esp32_s3_simulator.worker_broker import OciWorkerBroker

IMAGE = "registry.example/esp32/worker@sha256:" + "c" * 64
SESSION_ID = "d" * 32


def _file(path: Path, payload: str, mode: int) -> Path:
    path.write_text(payload, encoding="utf-8")
    path.chmod(mode)
    return path


def _broker_settings(tmp_path: Path) -> OciBrokerSettings:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(mode=0o770)
    runtime_root.chmod(0o770)
    socket_parent = tmp_path / "broker"
    socket_parent.mkdir(mode=0o770)
    socket_parent.chmod(0o770)
    docker = _file(
        tmp_path / "fake-docker",
        "#!/bin/sh\n"
        "case \" $* \" in\n"
        "  *\"SecurityOptions\"*) "
        "printf '[\"name=rootless\",\"name=seccomp,profile=builtin\"]' ;;\n"
        "  *\"CgroupVersion\"*) printf '2' ;;\n"
        "  *\" image inspect \"*) "
        "printf 'sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee' ;;\n"
        "  *\" run \"*) printf 'worker-serial'; printf 'worker-trace\\n' >&2 ;;\n"
        "esac\n"
        "exit 0\n",
        0o755,
    )
    seccomp = _file(tmp_path / "seccomp.json", "{}\n", 0o644)
    return OciBrokerSettings(
        socket_path=socket_parent / "worker.sock",
        runtime_root=runtime_root,
        docker_executable=docker,
        docker_host=f"unix:///run/user/{os.getuid()}/docker.sock",
        image_reference=IMAGE,
        seccomp_profile_path=seccomp,
        apparmor_profile="esp32-s3-worker",
        allowed_core_uid=os.getuid(),
        shared_group_gid=os.getgid(),
        max_workers=1,
        allow_same_identity_for_tests=True,
    )


def _create_session(settings: OciBrokerSettings) -> StartRequest:
    request = StartRequest(session_id=SESSION_ID, board_id="sticks3")
    directory = settings.runtime_root / SESSION_ID
    directory.mkdir(mode=0o770)
    directory.chmod(0o770)
    flash = directory / "flash.bin"
    with flash.open("wb") as output:
        output.truncate(8 * 1024 * 1024)
    flash.chmod(0o660)
    return request


async def test_broker_accepts_only_narrow_launch_and_relays_worker_io(tmp_path: Path) -> None:
    settings = _broker_settings(tmp_path)
    request = _create_session(settings)
    broker = OciWorkerBroker(settings)
    await broker.start()
    try:
        assert settings.socket_path.stat().st_mode & 0o777 == 0o660
        assert await probe_broker(settings.socket_path)
        process = await connect_broker_worker(settings.socket_path, request)
        assert await process.stdout.readexactly(len(b"worker-serial")) == b"worker-serial"
        assert await process.stderr.readline() == b"worker-trace\n"
        assert await process.wait() == 0
    finally:
        await broker.close()

    assert broker.active_count == 0
    assert not settings.socket_path.exists()


async def test_broker_runtime_verification_fails_without_rootless_mode(tmp_path: Path) -> None:
    settings = _broker_settings(tmp_path)
    settings.docker_executable.write_text(
        "#!/bin/sh\nprintf '[\"name=seccomp,profile=builtin\"]'\n",
        encoding="utf-8",
    )
    settings.docker_executable.chmod(0o755)
    broker = OciWorkerBroker(settings)

    with pytest.raises(OciPolicyError, match="not rootless"):
        await broker.verify_runtime()


async def test_session_manager_uses_broker_without_docker_authority(tmp_path: Path) -> None:
    broker_settings = _broker_settings(tmp_path)
    core_settings = Settings(
        runtime_root=broker_settings.runtime_root,
        qemu_executable=tmp_path / "not-used-qemu",
        rom_directory=tmp_path / "not-used-roms",
        native_workers_enabled=True,
        worker_sandbox_mode=WorkerSandboxMode.OCI_BROKER,
        worker_broker_socket=broker_settings.socket_path,
        worker_shared_group_gid=os.getgid(),
    )
    manager = SessionManager(core_settings)
    await manager.start()
    broker = OciWorkerBroker(broker_settings)
    await broker.start()
    try:
        firmware = bytes((0xE9, 1, 0, 0)) + bytes(4092)
        session = await manager.create(CARDPUTER_ADV, firmware)
        assert _stat_mode(session.runtime_directory) == 0o2770
        assert _stat_mode(session.flash_path) == 0o660
        assert session.runtime_directory.stat().st_gid == os.getgid()
        assert session.flash_path.stat().st_gid == os.getgid()
        assert session.process is not None
        assert await session.process.wait() == 0
    finally:
        await manager.close()
        await broker.close()


async def test_broker_shutdown_kills_attached_workers(tmp_path: Path) -> None:
    settings = _broker_settings(tmp_path)
    script = settings.docker_executable.read_text(encoding="utf-8")
    script = script.replace(
        "printf 'worker-serial'; printf 'worker-trace\\n' >&2",
        "exec sleep 60",
    )
    settings.docker_executable.write_text(script, encoding="utf-8")
    settings.docker_executable.chmod(0o755)
    request = _create_session(settings)
    broker = OciWorkerBroker(settings)
    await broker.start()

    process = await connect_broker_worker(settings.socket_path, request)
    assert broker.active_count == 1
    await broker.close()

    assert await asyncio.wait_for(process.wait(), timeout=2) != 0
    assert broker.active_count == 0


def _stat_mode(path: Path) -> int:
    return path.stat().st_mode & 0o7777
