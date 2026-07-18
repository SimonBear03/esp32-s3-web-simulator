# SPDX-License-Identifier: GPL-2.0-only

from dataclasses import dataclass


class FramebufferError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RGBFrame:
    width: int
    height: int
    pixels: bytes

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
        raise FramebufferError(
            f"framebuffer payload has {len(pixels)} bytes; expected {expected_size}"
        )
    return RGBFrame(width=width, height=height, pixels=pixels)
