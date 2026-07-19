# SPDX-License-Identifier: GPL-2.0-only

from pathlib import Path

import pytest

from esp32_s3_simulator.qemu import WorkerSandboxMode
from esp32_s3_simulator.sessions import SessionManager
from esp32_s3_simulator.settings import Settings


def test_settings_parse_production_worker_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMULATOR_WORKER_SANDBOX_MODE", "bubblewrap")
    monkeypatch.setenv("SIMULATOR_WORKER_SANDBOX_EXECUTABLE", "/opt/bin/bwrap")
    monkeypatch.setenv(
        "SIMULATOR_WORKER_SANDBOX_READONLY_PATHS",
        "/usr:/lib:/opt/simulator",
    )

    settings = Settings.from_environment()

    assert settings.worker_sandbox_mode is WorkerSandboxMode.BUBBLEWRAP
    assert settings.worker_sandbox_executable == Path("/opt/bin/bwrap")
    assert settings.worker_sandbox_readonly_paths == (
        Path("/usr"),
        Path("/lib"),
        Path("/opt/simulator"),
    )


def test_settings_reject_unknown_worker_sandbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIMULATOR_WORKER_SANDBOX_MODE", "wishful-thinking")

    with pytest.raises(ValueError, match="wishful-thinking"):
        Settings.from_environment()


def test_worker_readiness_fails_closed_without_configured_sandbox(tmp_path: Path) -> None:
    qemu = tmp_path / "qemu-system-xtensa"
    qemu.touch()
    roms = tmp_path / "roms"
    roms.mkdir()
    settings = Settings(
        runtime_root=tmp_path / "runtime",
        qemu_executable=qemu,
        rom_directory=roms,
        native_workers_enabled=True,
        worker_sandbox_mode=WorkerSandboxMode.BUBBLEWRAP,
        worker_sandbox_executable=tmp_path / "missing-bwrap",
    )

    assert SessionManager(settings).worker_ready is False
