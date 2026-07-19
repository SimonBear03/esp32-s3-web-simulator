# SPDX-License-Identifier: GPL-2.0-only

import os
from dataclasses import replace
from pathlib import Path

import pytest

from esp32_s3_simulator.broker_protocol import StartRequest
from esp32_s3_simulator.oci import MANAGED_LABEL, OciBrokerSettings, OciPolicyError

IMAGE = "registry.example/esp32/worker@sha256:" + "a" * 64
SESSION_ID = "b" * 32


def _regular_file(path: Path, *, executable: bool = False) -> Path:
    path.write_text("placeholder", encoding="utf-8")
    path.chmod(0o755 if executable else 0o644)
    return path


def _settings(tmp_path: Path) -> OciBrokerSettings:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(mode=0o770)
    runtime_root.chmod(0o770)
    socket_parent = tmp_path / "broker"
    socket_parent.mkdir(mode=0o770)
    socket_parent.chmod(0o770)
    return OciBrokerSettings(
        socket_path=socket_parent / "worker.sock",
        runtime_root=runtime_root,
        docker_executable=_regular_file(tmp_path / "docker", executable=True),
        docker_host=f"unix:///run/user/{os.getuid()}/docker.sock",
        image_reference=IMAGE,
        seccomp_profile_path=_regular_file(tmp_path / "seccomp.json"),
        apparmor_profile="esp32-s3-worker",
        allowed_core_uid=os.getuid(),
        shared_group_gid=os.getgid(),
        allow_same_identity_for_tests=True,
    )


def _session(settings: OciBrokerSettings, *, mode: int = 0o770) -> StartRequest:
    request = StartRequest(session_id=SESSION_ID, board_id="cardputer-adv")
    directory = settings.runtime_root / request.session_id
    directory.mkdir(mode=mode)
    directory.chmod(mode)
    flash = directory / "flash.bin"
    with flash.open("wb") as output:
        output.truncate(8 * 1024 * 1024)
    flash.chmod(0o660)
    return request


def test_oci_command_is_fixed_digest_pinned_and_drops_host_authority(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    request = _session(settings)

    settings.validate()
    command = settings.build_worker_command(request)

    assert command[:3] == (
        str(settings.docker_executable),
        "--host",
        f"unix:///run/user/{os.getuid()}/docker.sock",
    )
    assert command.count("--mount") == 1
    mount = command[command.index("--mount") + 1]
    assert mount == (
        f"type=bind,src={settings.runtime_root / SESSION_ID},"
        "dst=/runtime,bind-propagation=rprivate"
    )
    assert IMAGE in command
    assert MANAGED_LABEL in command
    assert "--network=none" in command
    assert "--ipc=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "no-new-privileges=true" in command
    assert f"seccomp={settings.seccomp_profile_path}" in command
    assert "apparmor=esp32-s3-worker" in command
    assert "--pids-limit" in command
    assert "--memory-swap" in command
    assert "--cpus" in command
    assert "--log-driver=none" in command
    assert "-sandbox" in command
    assert (
        command[command.index("-sandbox") + 1]
        == "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny"
    )
    assert "/var/run/docker.sock" not in " ".join(command)
    assert "--privileged" not in command
    assert "--device" not in command


def test_oci_policy_rejects_mutable_images_and_remote_docker(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    replace(settings, image_reference="sha256:" + "f" * 64).validate()
    with pytest.raises(OciPolicyError, match="immutable sha256"):
        replace(settings, image_reference="registry.example/esp32/worker:latest").validate()
    with pytest.raises(OciPolicyError, match="rootless Unix socket"):
        replace(settings, docker_host="tcp://127.0.0.1:2375").validate()


def test_oci_policy_requires_separate_core_and_broker_identities(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with pytest.raises(OciPolicyError, match="different operating-system identities"):
        replace(settings, allow_same_identity_for_tests=False).validate()


def test_oci_policy_rejects_symlink_escape_and_weak_permissions(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (settings.runtime_root / SESSION_ID).symlink_to(outside, target_is_directory=True)
    request = StartRequest(session_id=SESSION_ID, board_id="cardputer-adv")

    with pytest.raises(OciPolicyError, match="escaped"):
        settings.session_directory(request)

    (settings.runtime_root / SESSION_ID).unlink()
    request = _session(settings, mode=0o777)
    with pytest.raises(OciPolicyError, match="permissions"):
        settings.session_directory(request)


def test_oci_policy_rejects_wrong_flash_size(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    request = _session(settings)
    (settings.runtime_root / SESSION_ID / "flash.bin").write_bytes(b"too small")

    with pytest.raises(OciPolicyError, match="size"):
        settings.build_worker_command(request)


def test_oci_control_surface_allows_only_fixed_actions(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    assert settings.control_command("kill", SESSION_ID)[-2:] == (
        "kill",
        f"esp32-s3-worker-{SESSION_ID}",
    )
    with pytest.raises(OciPolicyError, match="not allowed"):
        settings.control_command("exec", SESSION_ID)
    with pytest.raises(Exception, match="32 lowercase"):
        settings.control_command("kill", "../another-container")
