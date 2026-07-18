# SPDX-License-Identifier: GPL-2.0-only

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
