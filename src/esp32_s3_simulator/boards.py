# SPDX-License-Identifier: GPL-2.0-only

from dataclasses import asdict, dataclass
from enum import StrEnum


class Fidelity(StrEnum):
    EMULATED = "emulated"
    BEHAVIORAL = "behavioral"
    PLANNED = "planned"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class Capability:
    id: str
    label: str
    fidelity: Fidelity
    note: str


@dataclass(frozen=True, slots=True)
class DisplayProfile:
    controller: str
    width: int
    height: int
    transport: str
    rotation_degrees: int


@dataclass(frozen=True, slots=True)
class BoardProfile:
    id: str
    label: str
    mcu: str
    flash_size_bytes: int
    psram_size_mib: int
    display: DisplayProfile
    capabilities: tuple[Capability, ...]

    def as_public_dict(self) -> dict[str, object]:
        return asdict(self)


CARDPUTER_ADV = BoardProfile(
    id="cardputer-adv",
    label="Cardputer ADV compatible",
    mcu="ESP32-S3FN8",
    flash_size_bytes=8 * 1024 * 1024,
    psram_size_mib=0,
    display=DisplayProfile(
        controller="ST7789",
        width=240,
        height=135,
        transport="SPI",
        rotation_degrees=90,
    ),
    capabilities=(
        Capability("cpu", "ESP32-S3 CPU and boot", Fidelity.EMULATED, "Espressif QEMU"),
        Capability("flash", "8 MiB SPI flash", Fidelity.EMULATED, "Patched GigaDevice QE path"),
        Capability("serial", "UART console", Fidelity.EMULATED, "Bidirectional byte stream"),
        Capability(
            "display",
            "ST7789 display",
            Fidelity.EMULATED,
            "SPI3 command/data model with RGB framebuffer capture",
        ),
        Capability(
            "keyboard",
            "TCA8418 keyboard",
            Fidelity.EMULATED,
            "I2C FIFO, GPIO 11 interrupt, and typed key injection",
        ),
        Capability(
            "imu",
            "BMI270 IMU",
            Fidelity.BEHAVIORAL,
            "I2C identification, configuration, and deterministic scripted samples",
        ),
        Capability(
            "power",
            "Battery voltage",
            Fidelity.BEHAVIORAL,
            "ADC1 GPIO10 battery-divider model; hardware has no charge-status telemetry",
        ),
        Capability("wifi", "Wi-Fi RF", Fidelity.UNSUPPORTED, "No physical RF simulation"),
        Capability("ble", "Bluetooth LE RF", Fidelity.UNSUPPORTED, "No physical RF simulation"),
    ),
)


STICKS3 = BoardProfile(
    id="sticks3",
    label="StickS3 compatible",
    mcu="ESP32-S3-PICO-1-N8R8",
    flash_size_bytes=8 * 1024 * 1024,
    psram_size_mib=8,
    display=DisplayProfile(
        controller="ST7789",
        width=135,
        height=240,
        transport="SPI",
        rotation_degrees=0,
    ),
    capabilities=(
        Capability("cpu", "ESP32-S3 CPU and boot", Fidelity.EMULATED, "Espressif QEMU"),
        Capability("flash", "8 MiB SPI flash", Fidelity.EMULATED, "Patched GigaDevice QE path"),
        Capability("psram", "8 MiB PSRAM", Fidelity.EMULATED, "QEMU SPI PSRAM model"),
        Capability("serial", "UART console", Fidelity.EMULATED, "Bidirectional byte stream"),
        Capability(
            "display",
            "ST7789 display",
            Fidelity.EMULATED,
            "SPI3 command/data model with RGB framebuffer capture",
        ),
        Capability(
            "buttons",
            "Physical buttons",
            Fidelity.EMULATED,
            "Active-low GPIO 11/12 transitions from typed button input",
        ),
        Capability(
            "imu",
            "BMI270 IMU",
            Fidelity.BEHAVIORAL,
            "I2C identification, configuration, and deterministic scripted samples",
        ),
        Capability(
            "power",
            "Battery and power states",
            Fidelity.BEHAVIORAL,
            "M5PM1 I2C registers with scripted voltage and charging state",
        ),
        Capability("wifi", "Wi-Fi RF", Fidelity.UNSUPPORTED, "No physical RF simulation"),
        Capability("ble", "Bluetooth LE RF", Fidelity.UNSUPPORTED, "No physical RF simulation"),
    ),
)


BOARD_PROFILES: dict[str, BoardProfile] = {
    CARDPUTER_ADV.id: CARDPUTER_ADV,
    STICKS3.id: STICKS3,
}


def get_board_profile(board_id: str) -> BoardProfile:
    try:
        return BOARD_PROFILES[board_id]
    except KeyError as error:
        raise ValueError(f"unknown board profile: {board_id}") from error
