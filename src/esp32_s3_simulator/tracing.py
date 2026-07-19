# SPDX-License-Identifier: GPL-2.0-only

import re

TRACE_EVENT_TYPES = {
    "i2c_event": "peripheral.i2c.event",
    "i2c_send": "peripheral.i2c.send",
    "i2c_send_async": "peripheral.i2c.send",
    "i2c_recv": "peripheral.i2c.receive",
    "i2c_ack": "peripheral.i2c.ack",
    "esp32s3_gpspi_transaction": "peripheral.spi.transaction",
    "st7789_command": "peripheral.display.command",
    "st7789_window": "peripheral.display.window",
    "esp32_gpio_input": "peripheral.gpio.input",
    "esp32_gpio_output": "peripheral.gpio.output",
    "tca8418_key_event": "peripheral.keyboard.event",
    "sticks3_button": "peripheral.button",
    "bmi270_sample": "peripheral.imu.sample",
    "m5pm1_power_state": "peripheral.power.state",
    "esp32s3_saradc_conversion": "peripheral.adc.conversion",
}

TRACE_EVENT_NAMES = tuple(TRACE_EVENT_TYPES)
TRACE_EVENT_LIMITS = {
    "i2c_event": 64,
    "i2c_send": 64,
    "i2c_send_async": 64,
    "i2c_recv": 64,
    "i2c_ack": 64,
    "esp32s3_gpspi_transaction": 128,
    "st7789_command": 128,
    "st7789_window": 64,
    "esp32_gpio_input": 128,
    "esp32_gpio_output": 128,
    "tca8418_key_event": 256,
    "sticks3_button": 256,
    "bmi270_sample": 256,
    "m5pm1_power_state": 256,
    "esp32s3_saradc_conversion": 64,
}
TRACE_LINE_PATTERN = re.compile(r"^(?:\d+@\d+\.\d+:)?(?P<name>[a-z0-9_]+)(?:\s+(?P<detail>.*))?$")
MAX_TRACE_LINE_BYTES = 2048
MAX_TRACE_DETAIL_CHARACTERS = 512


def parse_worker_trace_line(payload: bytes) -> tuple[str, dict[str, object]] | None:
    if not payload or len(payload) > MAX_TRACE_LINE_BYTES:
        return None
    text = payload.decode("ascii", errors="replace").strip()
    match = TRACE_LINE_PATTERN.fullmatch(text)
    if match is None:
        return None
    name = match.group("name")
    event_type = TRACE_EVENT_TYPES.get(name)
    if event_type is None:
        return None
    return event_type, {
        "trace_event": name,
        "detail": (match.group("detail") or "")[:MAX_TRACE_DETAIL_CHARACTERS],
    }
