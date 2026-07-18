# SPDX-License-Identifier: GPL-2.0-only

import pytest

from esp32_s3_simulator.boards import CARDPUTER_ADV
from esp32_s3_simulator.firmware import FirmwareValidationError, validate_and_pad_firmware


def merged_image(size: int = 4096) -> bytes:
    return bytes((0xE9, 3, 0, 0)) + bytes(size - 4)


def test_merged_image_is_padded_to_exact_board_flash_size() -> None:
    source = merged_image()
    flash, metadata = validate_and_pad_firmware(source, CARDPUTER_ADV)

    assert flash.startswith(source)
    assert len(flash) == CARDPUTER_ADV.flash_size_bytes
    assert flash[-1] == 0xFF
    assert metadata.source_size_bytes == len(source)
    assert metadata.flash_size_bytes == CARDPUTER_ADV.flash_size_bytes
    assert metadata.segment_count == 3
    assert metadata.source_sha256 != metadata.flash_sha256


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"\x7fELF" + bytes(4092), "ELF uploads are not bootable yet"),
        (bytes(4096), "must begin with image magic"),
        (bytes((0xE9, 0, 0, 0)) + bytes(4092), "invalid segment count"),
        (bytes((0xE9, 1, 9, 0)) + bytes(4092), "invalid flash mode"),
    ],
)
def test_invalid_firmware_is_rejected(payload: bytes, message: str) -> None:
    with pytest.raises(FirmwareValidationError, match=message):
        validate_and_pad_firmware(payload, CARDPUTER_ADV)


def test_oversized_firmware_is_rejected() -> None:
    payload = merged_image(CARDPUTER_ADV.flash_size_bytes + 1)
    with pytest.raises(FirmwareValidationError, match="exceeds"):
        validate_and_pad_firmware(payload, CARDPUTER_ADV)
