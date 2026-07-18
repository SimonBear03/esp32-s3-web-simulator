# SPDX-License-Identifier: GPL-2.0-only

import pytest

from esp32_s3_simulator.boards import CARDPUTER_ADV, STICKS3
from esp32_s3_simulator.inputs import BoardInputError, qmp_key_event


def test_cardputer_key_is_translated_to_typed_qmp_input() -> None:
    assert qmp_key_event(CARDPUTER_ADV, "a", True) == {
        "events": [
            {
                "type": "key",
                "data": {
                    "down": True,
                    "key": {"type": "qcode", "data": "a"},
                },
            }
        ]
    }
    assert qmp_key_event(CARDPUTER_ADV, "fn", False)["events"][0]["data"]["key"] == {
        "type": "qcode",
        "data": "meta_l",
    }


@pytest.mark.parametrize("board,key", [(CARDPUTER_ADV, "escape"), (STICKS3, "a")])
def test_unsupported_board_inputs_fail_closed(board: object, key: str) -> None:
    with pytest.raises(BoardInputError):
        qmp_key_event(board, key, True)  # type: ignore[arg-type]
