# SPDX-License-Identifier: GPL-2.0-only

import math
from typing import Any

from .boards import BoardProfile


class BoardInputError(ValueError):
    pass


CARDPUTER_KEY_TO_QCODE = {
    "grave": "grave_accent",
    **{str(number): str(number) for number in range(10)},
    "minus": "minus",
    "equals": "equal",
    "backspace": "backspace",
    "tab": "tab",
    **{letter: letter for letter in "qwertyuiop"},
    "bracket-left": "bracket_left",
    "bracket-right": "bracket_right",
    "backslash": "backslash",
    "fn": "meta_l",
    "shift": "shift",
    **{letter: letter for letter in "asdfghjkl"},
    "semicolon": "semicolon",
    "apostrophe": "apostrophe",
    "enter": "ret",
    "ctrl": "ctrl",
    "opt": "meta_r",
    "alt": "alt",
    **{letter: letter for letter in "zxcvbnm"},
    "comma": "comma",
    "period": "dot",
    "slash": "slash",
    "space": "spc",
}

STICKS3_BUTTONS = frozenset({"a", "b"})
STICKS3_BUTTONS_PATH = "/machine/peripheral/sticks3-buttons"
STICKS3_IMU_PATH = "/machine/peripheral/sticks3-imu"
STICKS3_PMIC_PATH = "/machine/peripheral/sticks3-pmic"


def qmp_key_event(board: BoardProfile, key: str, pressed: bool) -> dict[str, Any]:
    if board.id != "cardputer-adv":
        raise BoardInputError(f"keyboard input is unavailable for board profile: {board.id}")
    try:
        qcode = CARDPUTER_KEY_TO_QCODE[key]
    except KeyError as error:
        raise BoardInputError(f"unknown Cardputer ADV key: {key}") from error

    return {
        "events": [
            {
                "type": "key",
                "data": {
                    "down": pressed,
                    "key": {"type": "qcode", "data": qcode},
                },
            }
        ]
    }


def qmp_button_event(board: BoardProfile, button: str, pressed: bool) -> dict[str, Any]:
    if board.id != "sticks3":
        raise BoardInputError(f"button input is unavailable for board profile: {board.id}")
    if button not in STICKS3_BUTTONS:
        raise BoardInputError(f"unknown StickS3 button: {button}")

    return {
        "path": STICKS3_BUTTONS_PATH,
        "property": f"button-{button}",
        "value": pressed,
    }


def qmp_imu_sample(
    board: BoardProfile,
    acceleration_g: tuple[float, float, float],
    angular_velocity_dps: tuple[float, float, float],
) -> dict[str, Any]:
    if board.id != "sticks3":
        raise BoardInputError(f"IMU input is unavailable for board profile: {board.id}")
    values = (*acceleration_g, *angular_velocity_dps)
    if not all(math.isfinite(value) for value in values):
        raise BoardInputError("StickS3 IMU values must be finite")
    if any(abs(value) > 16 for value in acceleration_g):
        raise BoardInputError("StickS3 acceleration exceeds the 16 g model range")
    if any(abs(value) > 2000 for value in angular_velocity_dps):
        raise BoardInputError("StickS3 angular velocity exceeds the 2000 dps model range")

    scaled = [round(value * 1000) for value in values]
    return {
        "path": STICKS3_IMU_PATH,
        "property": "sample",
        "value": ",".join(str(value) for value in scaled),
    }


def qmp_power_state(
    board: BoardProfile, battery_mv: int, vin_mv: int, charging: bool
) -> dict[str, Any]:
    if board.id != "sticks3":
        raise BoardInputError(f"power input is unavailable for board profile: {board.id}")
    if not 0 <= battery_mv <= 6000 or not 0 <= vin_mv <= 6000:
        raise BoardInputError("StickS3 voltage must be between 0 and 6000 mV")
    return {
        "path": STICKS3_PMIC_PATH,
        "property": "power-state",
        "value": f"{battery_mv},{vin_mv},{int(charging)}",
    }
