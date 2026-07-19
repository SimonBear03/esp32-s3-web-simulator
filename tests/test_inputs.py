# SPDX-License-Identifier: GPL-2.0-only

import pytest

from esp32_s3_simulator.boards import CARDPUTER_ADV, STICKS3
from esp32_s3_simulator.inputs import (
    BoardInputError,
    qmp_button_event,
    qmp_imu_sample,
    qmp_key_event,
    qmp_power_state,
)


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


def test_sticks3_buttons_are_translated_to_typed_qmp_input() -> None:
    assert qmp_button_event(STICKS3, "b", True) == {
        "path": "/machine/peripheral/sticks3-buttons",
        "property": "button-b",
        "value": True,
    }
    with pytest.raises(BoardInputError, match="unknown StickS3 button"):
        qmp_button_event(STICKS3, "power", True)
    with pytest.raises(BoardInputError, match="unavailable"):
        qmp_button_event(CARDPUTER_ADV, "a", True)


def test_sticks3_sensor_and_power_inputs_use_private_qom_properties() -> None:
    assert qmp_imu_sample(
        STICKS3, (1.25, -0.5, 0.0), (0.0, 45.5, -250.0)
    ) == {
        "path": "/machine/peripheral/sticks3-imu",
        "property": "sample",
        "value": "1250,-500,0,0,45500,-250000",
    }
    assert qmp_power_state(STICKS3, 3700, 0, False) == {
        "path": "/machine/peripheral/sticks3-pmic",
        "property": "power-state",
        "value": "3700,0,0",
    }


def test_cardputer_sensor_and_adc_battery_inputs_use_board_qom_properties() -> None:
    assert qmp_imu_sample(
        CARDPUTER_ADV, (0.0, -1.0, 0.5), (12.0, 0.0, -250.0)
    ) == {
        "path": "/machine/peripheral/cardputer-adv-imu",
        "property": "sample",
        "value": "0,-1000,500,12000,0,-250000",
    }
    assert qmp_power_state(CARDPUTER_ADV, 3700, 0, False) == {
        "path": "/machine/soc/saradc",
        "property": "adc1-ch9-millivolts",
        "value": 1850,
    }


def test_cardputer_power_rejects_telemetry_the_hardware_cannot_report() -> None:
    with pytest.raises(BoardInputError, match="battery voltage only"):
        qmp_power_state(CARDPUTER_ADV, 3900, 5000, True)


def test_sensor_and_power_values_are_range_checked() -> None:
    with pytest.raises(BoardInputError, match="16 g"):
        qmp_imu_sample(STICKS3, (17.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    with pytest.raises(BoardInputError, match="6000 mV"):
        qmp_power_state(STICKS3, 7000, 0, False)
