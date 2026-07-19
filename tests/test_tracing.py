# SPDX-License-Identifier: GPL-2.0-only

from esp32_s3_simulator.tracing import parse_worker_trace_line


def test_worker_trace_parser_accepts_only_bounded_known_events() -> None:
    assert parse_worker_trace_line(
        b"123@1721379600.123456:esp32_gpio_input pin=11 level=0 interrupt=1\n"
    ) == (
        "peripheral.gpio.input",
        {
            "trace_event": "esp32_gpio_input",
            "detail": "pin=11 level=0 interrupt=1",
        },
    )
    assert parse_worker_trace_line(b"i2c_send send(addr:0x34) data:0x24\n") == (
        "peripheral.i2c.send",
        {
            "trace_event": "i2c_send",
            "detail": "send(addr:0x34) data:0x24",
        },
    )
    assert parse_worker_trace_line(b"qemu-system-xtensa: private/path warning\n") is None
    assert parse_worker_trace_line(b"x" * 2049) is None
