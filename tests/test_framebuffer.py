# SPDX-License-Identifier: GPL-2.0-only

import pytest

from esp32_s3_simulator.framebuffer import FramebufferError, parse_qemu_ppm


def test_qemu_ppm_is_parsed_as_addressable_rgb_frame() -> None:
    frame = parse_qemu_ppm(b"P6\n2 1\n255\n" + bytes((255, 0, 0, 0, 0, 255)))

    assert (frame.width, frame.height) == (2, 1)
    assert frame.pixel(0, 0) == (255, 0, 0)
    assert frame.pixel(1, 0) == (0, 0, 255)


@pytest.mark.parametrize(
    "payload",
    (
        b"P3\n1 1\n255\n000",
        b"P6\n0 1\n255\n",
        b"P6\n1 1\n15\n000",
        b"P6\n1 1\n255\n00",
    ),
)
def test_invalid_or_unsupported_qemu_ppm_is_rejected(payload: bytes) -> None:
    with pytest.raises(FramebufferError):
        parse_qemu_ppm(payload)


def test_pixel_bounds_are_enforced() -> None:
    frame = parse_qemu_ppm(b"P6\n1 1\n255\n000")

    with pytest.raises(IndexError):
        frame.pixel(1, 0)
