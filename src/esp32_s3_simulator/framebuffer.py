# SPDX-License-Identifier: GPL-2.0-only

from dataclasses import dataclass
from struct import Struct


class FramebufferError(ValueError):
    pass


FRAMEBUFFER_MAGIC = b"ESPF"
FRAMEBUFFER_PROTOCOL_VERSION = 1
FRAMEBUFFER_PIXEL_FORMAT_RGB24 = 1
FRAMEBUFFER_HEADER = Struct(">4sBBHHI")


@dataclass(frozen=True, slots=True)
class RGBFrame:
    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        if not 1 <= self.width <= 0xFFFF or not 1 <= self.height <= 0xFFFF:
            raise FramebufferError("framebuffer dimensions are outside uint16 range")
        if len(self.pixels) != self.width * self.height * 3:
            raise FramebufferError("framebuffer pixel length does not match its dimensions")

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        if not 0 <= x < self.width or not 0 <= y < self.height:
            raise IndexError(f"pixel ({x}, {y}) is outside {self.width}x{self.height}")
        offset = (y * self.width + x) * 3
        return tuple(self.pixels[offset : offset + 3])  # type: ignore[return-value]


def parse_qemu_ppm(payload: bytes) -> RGBFrame:
    """Parse the fixed P6 framebuffer format emitted by QEMU screendump."""
    try:
        magic, dimensions, maximum, pixels = payload.split(b"\n", 3)
        width_text, height_text = dimensions.split()
        width = int(width_text)
        height = int(height_text)
        maximum_value = int(maximum)
    except (ValueError, TypeError) as error:
        raise FramebufferError("invalid QEMU PPM header") from error

    if magic != b"P6" or maximum_value != 255 or width <= 0 or height <= 0:
        raise FramebufferError("unsupported QEMU PPM format")
    expected_size = width * height * 3
    if len(pixels) != expected_size:
        packed_row_size = width * 3
        qemu_row_stride = (packed_row_size + 3) & ~3
        if len(pixels) == qemu_row_stride * height:
            pixels = b"".join(
                pixels[row * qemu_row_stride : row * qemu_row_stride + packed_row_size]
                for row in range(height)
            )
        else:
            raise FramebufferError(
                f"framebuffer payload has {len(pixels)} bytes; expected {expected_size}"
            )
    return RGBFrame(width=width, height=height, pixels=pixels)


def encode_framebuffer_packet(frame: RGBFrame, sequence: int) -> bytes:
    if not 0 <= sequence <= 0xFFFFFFFF:
        raise FramebufferError("framebuffer sequence is outside uint32 range")
    return FRAMEBUFFER_HEADER.pack(
        FRAMEBUFFER_MAGIC,
        FRAMEBUFFER_PROTOCOL_VERSION,
        FRAMEBUFFER_PIXEL_FORMAT_RGB24,
        frame.width,
        frame.height,
        sequence,
    ) + frame.pixels


def parse_framebuffer_packet(payload: bytes) -> tuple[int, RGBFrame]:
    if len(payload) < FRAMEBUFFER_HEADER.size:
        raise FramebufferError("framebuffer packet is shorter than its header")
    magic, version, pixel_format, width, height, sequence = FRAMEBUFFER_HEADER.unpack_from(payload)
    if magic != FRAMEBUFFER_MAGIC or version != FRAMEBUFFER_PROTOCOL_VERSION:
        raise FramebufferError("unsupported framebuffer packet version")
    if pixel_format != FRAMEBUFFER_PIXEL_FORMAT_RGB24:
        raise FramebufferError("unsupported framebuffer pixel format")
    pixels = payload[FRAMEBUFFER_HEADER.size :]
    if len(pixels) != width * height * 3:
        raise FramebufferError("framebuffer packet pixel length is invalid")
    return sequence, RGBFrame(width=width, height=height, pixels=pixels)
