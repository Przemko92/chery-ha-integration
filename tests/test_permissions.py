from custom_components.chery_europe.exceptions import CheryEuropePermissionError
from custom_components.chery_europe.permissions import (
    adapt_command,
    category_denied,
    normalize_permissions,
)

import pytest


def test_normalize_permissions():
    perms = normalize_permissions(
        {"data": {"permissionList": [{"id": 205, "state": 1}, {"id": 214, "state": 0}]}}
    )
    assert perms[205] == 1
    assert perms[214] == 0


def test_category_denied_unknown_is_allowed():
    assert category_denied("seatControl", {}) is False


def test_category_denied_when_closed():
    assert category_denied("seatControl", {214: 0}) is True


def test_adapt_command_raises_when_category_denied():
    with pytest.raises(CheryEuropePermissionError):
        adapt_command("findCar", {}, {202: 0})


def test_adapt_command_reroutes_seat_to_air_control():
    endpoint, body = adapt_command(
        "seatControl",
        {"mSeatHeating": "3", "times": "15"},
        {214: 0, 2141: 0, 204: 1, 2047: 1, 2041: 1},
    )
    assert endpoint == "airControl"
    assert body["airControlType"] == "1"
    assert body["mSeatHeating"] == "3"


def test_adapt_command_blocks_weekly_charge_cycle():
    with pytest.raises(CheryEuropePermissionError):
        adapt_command(
            "chargeAppointControl",
            {
                "mainSwitch": 1,
                "chargeAppointPlans": [{"cycleData": [1, 2, 3, 4, 5, 6, 7]}],
            },
            {213: 1, 2132: 0, 2131: 1},
        )
