# SPDX-License-Identifier: GPL-2.0-only

from esp32_s3_simulator.boards import BOARD_PROFILES, Fidelity, get_board_profile


def test_initial_board_profiles_have_explicit_fidelity() -> None:
    assert set(BOARD_PROFILES) == {"cardputer-adv", "sticks3"}

    cardputer = get_board_profile("cardputer-adv")
    sticks3 = get_board_profile("sticks3")

    assert cardputer.flash_size_bytes == 8 * 1024 * 1024
    assert cardputer.psram_size_mib == 0
    assert sticks3.psram_size_mib == 8
    assert all(capability.fidelity in Fidelity for capability in cardputer.capabilities)
    assert any(
        capability.id == "keyboard" and capability.fidelity is Fidelity.PLANNED
        for capability in cardputer.capabilities
    )


def test_unknown_board_is_rejected() -> None:
    try:
        get_board_profile("unknown")
    except ValueError as error:
        assert str(error) == "unknown board profile: unknown"
    else:
        raise AssertionError("unknown board profile was accepted")
