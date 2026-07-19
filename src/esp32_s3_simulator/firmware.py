# SPDX-License-Identifier: GPL-2.0-only

import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .boards import BoardProfile

ESP_IMAGE_MAGIC = 0xE9
ELF_MAGIC = b"\x7fELF"
MINIMUM_IMAGE_SIZE = 4 * 1024
MAXIMUM_SEGMENTS = 16


class FirmwareValidationError(ValueError):
    """Raised when an upload is not a usable merged ESP flash image."""


@dataclass(frozen=True, slots=True)
class ValidatedFirmware:
    source_size_bytes: int
    flash_size_bytes: int
    source_sha256: str
    flash_sha256: str
    segment_count: int
    flash_mode: int


def validate_and_pad_firmware(
    payload: bytes, board: BoardProfile
) -> tuple[bytes, ValidatedFirmware]:
    if payload.startswith(ELF_MAGIC):
        raise FirmwareValidationError(
            "ELF uploads are not bootable yet; upload a merged flash image starting at offset 0"
        )
    if len(payload) < MINIMUM_IMAGE_SIZE:
        raise FirmwareValidationError("firmware image is too small to be a merged ESP32-S3 image")
    if len(payload) > board.flash_size_bytes:
        raise FirmwareValidationError(
            f"firmware image exceeds the {board.flash_size_bytes}-byte board flash capacity"
        )
    if payload[0] != ESP_IMAGE_MAGIC:
        raise FirmwareValidationError("merged ESP32-S3 image must begin with image magic 0xE9")

    segment_count = payload[1]
    if not 1 <= segment_count <= MAXIMUM_SEGMENTS:
        raise FirmwareValidationError("ESP image header contains an invalid segment count")

    flash_mode = payload[2]
    if flash_mode > 3:
        raise FirmwareValidationError("ESP image header contains an invalid flash mode")

    normalized = payload.ljust(board.flash_size_bytes, b"\xff")
    metadata = ValidatedFirmware(
        source_size_bytes=len(payload),
        flash_size_bytes=len(normalized),
        source_sha256=sha256(payload).hexdigest(),
        flash_sha256=sha256(normalized).hexdigest(),
        segment_count=segment_count,
        flash_mode=flash_mode,
    )
    return normalized, metadata


def write_private_flash_image(
    path: Path,
    payload: bytes,
    *,
    directory_mode: int = 0o700,
    file_mode: int = 0o600,
    group_gid: int | None = None,
) -> None:
    path.parent.mkdir(mode=directory_mode, parents=True, exist_ok=False)
    path.parent.chmod(directory_mode)
    if group_gid is not None:
        os.chown(path.parent, -1, group_gid)
    path.write_bytes(payload)
    path.chmod(file_mode)
    if group_gid is not None:
        os.chown(path, -1, group_gid)
