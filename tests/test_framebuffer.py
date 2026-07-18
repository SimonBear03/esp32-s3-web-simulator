# SPDX-License-Identifier: GPL-2.0-only

import pytest

from esp32_s3_simulator.framebuffer import (
    FramebufferError,
    RGBFrame,
    encode_framebuffer_packet,
    parse_framebuffer_packet,
    parse_qemu_ppm,
)


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


def test_qemu_ppm_row_alignment_is_removed_for_sticks3_widths() -> None:
    red_row = bytes((255, 0, 0)) * 135 + b"\x00\x00\x00"
    blue_row = bytes((0, 0, 255)) * 135 + b"\x00\x00\x00"

    frame = parse_qemu_ppm(b"P6\n135 2\n255\n" + red_row + blue_row)

    assert len(frame.pixels) == 135 * 2 * 3
    assert frame.pixel(134, 0) == (255, 0, 0)
    assert frame.pixel(0, 1) == (0, 0, 255)


def test_pixel_bounds_are_enforced() -> None:
    frame = parse_qemu_ppm(b"P6\n1 1\n255\n000")

    with pytest.raises(IndexError):
        frame.pixel(1, 0)


def test_binary_web_packet_round_trips_dimensions_sequence_and_pixels() -> None:
    frame = parse_qemu_ppm(b"P6\n2 1\n255\n" + bytes((255, 0, 0, 0, 0, 255)))

    sequence, decoded = parse_framebuffer_packet(encode_framebuffer_packet(frame, 42))

    assert sequence == 42
    assert decoded == frame


def test_invalid_binary_web_packet_is_rejected() -> None:
    with pytest.raises(FramebufferError):
        parse_framebuffer_packet(b"ESPF")


def test_rgb_frame_rejects_inconsistent_dimensions() -> None:
    with pytest.raises(FramebufferError, match="pixel length"):
        RGBFrame(width=2, height=1, pixels=bytes((1, 2, 3)))
