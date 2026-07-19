# SPDX-License-Identifier: GPL-2.0-only

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .boards import BOARD_PROFILES
from .broker_protocol import StartRequest
from .qemu import QemuWorkerConfig, build_qemu_process_command

_IMAGE_REFERENCE = re.compile(
    r"(?:"
    r"[a-z0-9][a-z0-9._-]*(?::[0-9]+)?/"
    r"[a-z0-9][a-z0-9._/-]*@sha256:"
    r"|sha256:"
    r")[0-9a-f]{64}"
)
_APPARMOR_PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_UNIX_DOCKER_HOST = re.compile(r"unix:///run/user/[1-9][0-9]*/docker\.sock")
_CONTAINER_NAME = re.compile(r"esp32-s3-worker-([0-9a-f]{32})")
MANAGED_LABEL = "com.zillionvisionary.esp32-simulator.managed=true"
SESSION_LABEL_PREFIX = "com.zillionvisionary.esp32-simulator.session="
CONTAINER_NAME_PREFIX = "esp32-s3-worker-"


class OciPolicyError(RuntimeError):
    """Raised when the fixed OCI policy cannot be proven safe."""


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise OciPolicyError(f"required broker setting is missing: {name}")
    return value


def _parse_integer(name: str, value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise OciPolicyError(f"broker setting is not an integer: {name}") from error
    if isinstance(parsed, bool):
        raise OciPolicyError(f"broker setting is not an integer: {name}")
    return parsed


def _parse_float(name: str, value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise OciPolicyError(f"broker setting is not a number: {name}") from error
    if not parsed.is_integer() and not (0.0 < parsed < 100.0):
        raise OciPolicyError(f"broker setting is not a finite number: {name}")
    return parsed


def _validate_cli_path(path: Path, *, label: str) -> Path:
    if not path.is_absolute():
        raise OciPolicyError(f"{label} must be an absolute path")
    try:
        path_stat = path.lstat()
    except FileNotFoundError as error:
        raise OciPolicyError(f"{label} does not exist") from error
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise OciPolicyError(f"{label} must be a non-symlink regular file")
    if path_stat.st_mode & 0o022:
        raise OciPolicyError(f"{label} must not be group- or world-writable")
    return path


def _validate_mount_text(value: str, *, label: str) -> None:
    if "," in value or any(ord(character) < 0x20 for character in value):
        raise OciPolicyError(f"{label} cannot be represented safely in Docker mount syntax")


@dataclass(frozen=True, slots=True)
class OciBrokerSettings:
    socket_path: Path
    runtime_root: Path
    docker_executable: Path
    docker_host: str
    image_reference: str
    seccomp_profile_path: Path
    apparmor_profile: str
    allowed_core_uid: int
    shared_group_gid: int
    max_workers: int = 2
    memory_mib: int = 1536
    cpus: float = 1.0
    pids_limit: int = 96
    tmpfs_mib: int = 16
    wall_time_seconds: int = 240
    stop_timeout_seconds: int = 3
    qemu_executable: Path = Path("/opt/esp32-s3/bin/qemu-system-xtensa")
    qemu_rom_directory: Path = Path("/opt/esp32-s3/share/qemu")
    allow_same_identity_for_tests: bool = False

    @classmethod
    def from_environment(cls) -> "OciBrokerSettings":
        settings = cls(
            socket_path=Path(
                os.environ.get(
                    "SIMULATOR_WORKER_BROKER_SOCKET",
                    "/run/esp32-simulator/worker-broker.sock",
                )
            ),
            runtime_root=Path(
                os.environ.get("SIMULATOR_RUNTIME_ROOT", "/run/esp32-simulator/sessions")
            ),
            docker_executable=Path(
                os.environ.get("SIMULATOR_ROOTLESS_DOCKER", "/usr/bin/docker")
            ),
            docker_host=_required_environment("SIMULATOR_ROOTLESS_DOCKER_HOST"),
            image_reference=_required_environment("SIMULATOR_WORKER_IMAGE"),
            seccomp_profile_path=Path(
                _required_environment("SIMULATOR_WORKER_SECCOMP_PROFILE")
            ),
            apparmor_profile=_required_environment("SIMULATOR_WORKER_APPARMOR_PROFILE"),
            allowed_core_uid=_parse_integer(
                "SIMULATOR_ALLOWED_CORE_UID",
                _required_environment("SIMULATOR_ALLOWED_CORE_UID"),
            ),
            shared_group_gid=_parse_integer(
                "SIMULATOR_SHARED_GROUP_GID",
                _required_environment("SIMULATOR_SHARED_GROUP_GID"),
            ),
            max_workers=_parse_integer(
                "SIMULATOR_BROKER_MAX_WORKERS",
                os.environ.get("SIMULATOR_BROKER_MAX_WORKERS", "2"),
            ),
            memory_mib=_parse_integer(
                "SIMULATOR_WORKER_MEMORY_MIB",
                os.environ.get("SIMULATOR_WORKER_MEMORY_MIB", "1536"),
            ),
            cpus=_parse_float(
                "SIMULATOR_WORKER_CPUS",
                os.environ.get("SIMULATOR_WORKER_CPUS", "1.0"),
            ),
            pids_limit=_parse_integer(
                "SIMULATOR_WORKER_PIDS",
                os.environ.get("SIMULATOR_WORKER_PIDS", "96"),
            ),
            tmpfs_mib=_parse_integer(
                "SIMULATOR_WORKER_TMPFS_MIB",
                os.environ.get("SIMULATOR_WORKER_TMPFS_MIB", "16"),
            ),
            wall_time_seconds=_parse_integer(
                "SIMULATOR_WORKER_WALL_SECONDS",
                os.environ.get("SIMULATOR_WORKER_WALL_SECONDS", "240"),
            ),
            stop_timeout_seconds=_parse_integer(
                "SIMULATOR_WORKER_STOP_SECONDS",
                os.environ.get("SIMULATOR_WORKER_STOP_SECONDS", "3"),
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.socket_path.is_absolute() or not self.runtime_root.is_absolute():
            raise OciPolicyError("broker socket and runtime root must be absolute paths")
        _validate_mount_text(str(self.runtime_root), label="runtime root")
        _validate_cli_path(self.docker_executable, label="Docker client")
        _validate_cli_path(self.seccomp_profile_path, label="seccomp profile")
        if (
            not _UNIX_DOCKER_HOST.fullmatch(self.docker_host)
            or self.docker_host != f"unix:///run/user/{os.getuid()}/docker.sock"
        ):
            raise OciPolicyError("Docker host must be a dedicated rootless Unix socket")
        if not _IMAGE_REFERENCE.fullmatch(self.image_reference):
            raise OciPolicyError("worker image must use an immutable sha256 digest")
        if not _APPARMOR_PROFILE.fullmatch(self.apparmor_profile):
            raise OciPolicyError("AppArmor profile name is invalid")
        if self.allowed_core_uid <= 0 or self.shared_group_gid <= 0:
            raise OciPolicyError("core UID and shared group GID must be non-root identities")
        if self.allowed_core_uid == os.getuid() and not self.allow_same_identity_for_tests:
            raise OciPolicyError("broker and core must use different operating-system identities")
        if not 1 <= self.max_workers <= 8:
            raise OciPolicyError("maximum workers must be between 1 and 8")
        if not 256 <= self.memory_mib <= 2048:
            raise OciPolicyError("worker memory must be between 256 and 2048 MiB")
        if not 0.1 <= self.cpus <= 2.0:
            raise OciPolicyError("worker CPUs must be between 0.1 and 2.0")
        if not 16 <= self.pids_limit <= 256:
            raise OciPolicyError("worker PID limit must be between 16 and 256")
        if not 1 <= self.tmpfs_mib <= 64:
            raise OciPolicyError("worker tmpfs must be between 1 and 64 MiB")
        if not 30 <= self.wall_time_seconds <= 900:
            raise OciPolicyError("worker wall time must be between 30 and 900 seconds")
        if not 1 <= self.stop_timeout_seconds <= 10:
            raise OciPolicyError("worker stop timeout must be between 1 and 10 seconds")
        for path, label in (
            (self.qemu_executable, "container QEMU executable"),
            (self.qemu_rom_directory, "container QEMU ROM directory"),
        ):
            if not path.is_absolute() or not str(path).startswith("/opt/esp32-s3/"):
                raise OciPolicyError(f"{label} must stay under /opt/esp32-s3")

    @property
    def docker_prefix(self) -> tuple[str, ...]:
        return (str(self.docker_executable), "--host", self.docker_host)

    def container_name(self, session_id: str) -> str:
        request = StartRequest(session_id=session_id, board_id=next(iter(BOARD_PROFILES)))
        return f"{CONTAINER_NAME_PREFIX}{request.session_id}"

    def session_directory(self, request: StartRequest) -> Path:
        try:
            root_stat = self.runtime_root.lstat()
            resolved_root = self.runtime_root.resolve(strict=True)
        except FileNotFoundError as error:
            raise OciPolicyError("runtime root is unavailable") from error
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise OciPolicyError("runtime root must be a non-symlink directory")
        root_mode = stat.S_IMODE(root_stat.st_mode)
        if (
            root_stat.st_uid != self.allowed_core_uid
            or root_stat.st_gid != self.shared_group_gid
            or root_mode & 0o007
            or root_mode & 0o070 != 0o070
        ):
            raise OciPolicyError("runtime root ownership or permissions are unsafe")
        expected = self.runtime_root / request.session_id
        try:
            directory_stat = expected.lstat()
            resolved_directory = expected.resolve(strict=True)
        except FileNotFoundError as error:
            raise OciPolicyError("session directory is unavailable") from error
        if (
            stat.S_ISLNK(directory_stat.st_mode)
            or not stat.S_ISDIR(directory_stat.st_mode)
            or resolved_directory.parent != resolved_root
            or resolved_directory != resolved_root / request.session_id
        ):
            raise OciPolicyError("session directory escaped the runtime root")
        if directory_stat.st_uid != self.allowed_core_uid:
            raise OciPolicyError("session directory has an unexpected owner")
        if directory_stat.st_gid != self.shared_group_gid:
            raise OciPolicyError("session directory has an unexpected group")
        mode = stat.S_IMODE(directory_stat.st_mode)
        if mode & 0o007 or mode & 0o070 != 0o070:
            raise OciPolicyError("session directory permissions do not match shared isolation")
        _validate_mount_text(str(resolved_directory), label="session directory")
        self._validate_flash(resolved_directory / "flash.bin", request)
        return resolved_directory

    def _validate_flash(self, flash_path: Path, request: StartRequest) -> None:
        try:
            flash_stat = flash_path.lstat()
        except FileNotFoundError as error:
            raise OciPolicyError("session flash image is unavailable") from error
        if stat.S_ISLNK(flash_stat.st_mode) or not stat.S_ISREG(flash_stat.st_mode):
            raise OciPolicyError("session flash image must be a non-symlink regular file")
        if flash_stat.st_uid != self.allowed_core_uid or flash_stat.st_gid != self.shared_group_gid:
            raise OciPolicyError("session flash image has unexpected ownership")
        flash_mode = stat.S_IMODE(flash_stat.st_mode)
        if flash_mode & 0o007 or flash_mode & 0o660 != 0o660:
            raise OciPolicyError("session flash image permissions do not match shared isolation")
        expected_size = BOARD_PROFILES[request.board_id].flash_size_bytes
        if flash_stat.st_size != expected_size:
            raise OciPolicyError("session flash image size does not match the board")

    def build_worker_command(self, request: StartRequest) -> tuple[str, ...]:
        session_directory = self.session_directory(request)
        board = BOARD_PROFILES[request.board_id]
        container_qemu = QemuWorkerConfig(
            executable=self.qemu_executable,
            rom_directory=self.qemu_rom_directory,
        )
        qemu_command = build_qemu_process_command(
            container_qemu,
            board,
            Path("/runtime/flash.bin"),
            Path("/runtime/qmp.sock"),
            Path("/runtime/gdb.sock"),
            True,
            seccomp_sandbox_enabled=True,
        )
        name = f"{CONTAINER_NAME_PREFIX}{request.session_id}"
        mount = (
            f"type=bind,src={session_directory},dst=/runtime,bind-propagation=rprivate"
        )
        return (
            *self.docker_prefix,
            "run",
            "--rm",
            "--interactive",
            "--pull=never",
            "--name",
            name,
            "--label",
            MANAGED_LABEL,
            "--label",
            f"{SESSION_LABEL_PREFIX}{request.session_id}",
            "--network=none",
            "--ipc=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--security-opt",
            f"seccomp={self.seccomp_profile_path}",
            "--security-opt",
            f"apparmor={self.apparmor_profile}",
            "--pids-limit",
            str(self.pids_limit),
            "--memory",
            f"{self.memory_mib}m",
            "--memory-swap",
            f"{self.memory_mib}m",
            "--cpus",
            str(self.cpus),
            "--ulimit",
            "nofile=64:64",
            "--ulimit",
            "fsize=67108864:67108864",
            "--stop-timeout",
            str(self.stop_timeout_seconds),
            "--stop-signal",
            "SIGTERM",
            "--log-driver=none",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,nodev,size={self.tmpfs_mib}m,mode=1777",
            "--mount",
            mount,
            "--workdir",
            "/runtime",
            "--env",
            "LANG=C.UTF-8",
            "--env",
            "PATH=/opt/esp32-s3/bin:/usr/bin:/bin",
            self.image_reference,
            *qemu_command,
        )

    def control_command(self, action: str, session_id: str) -> tuple[str, ...]:
        if action not in {"stop", "kill", "rm"}:
            raise OciPolicyError("Docker control action is not allowed")
        name = self.container_name(session_id)
        if action == "stop":
            return (*self.docker_prefix, "stop", "--time", str(self.stop_timeout_seconds), name)
        if action == "rm":
            return (*self.docker_prefix, "rm", "--force", name)
        return (*self.docker_prefix, "kill", name)

    def list_managed_command(self) -> tuple[str, ...]:
        return (
            *self.docker_prefix,
            "ps",
            "--all",
            "--format",
            "{{.Names}}",
            "--filter",
            f"label={MANAGED_LABEL}",
        )

    @staticmethod
    def session_id_from_container_name(value: str) -> str:
        match = _CONTAINER_NAME.fullmatch(value)
        if match is None:
            raise OciPolicyError("Docker returned an invalid managed container name")
        return match.group(1)
