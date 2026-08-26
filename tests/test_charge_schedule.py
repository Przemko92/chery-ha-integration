# pyright: reportArgumentType=false
"""Tests for local charge schedule minute helpers."""

from datetime import time

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.charge_schedule import (
    format_minutes_as_hhmm,
    local_time_to_minutes,
    minutes_to_local_time,
    plan_duration_hours,
    plan_start_time,
)


def test_local_time_round_trip():
    assert local_time_to_minutes(time(22, 0)) == 1320
    assert minutes_to_local_time(1320) == time(22, 0)
    assert format_minutes_as_hhmm(1320) == "22:00"


def test_local_midnight_and_quarter():
    assert local_time_to_minutes(time(0, 0)) == 0
    assert minutes_to_local_time(0) == time(0, 0)
    assert format_minutes_as_hhmm(465) == "07:45"
    assert minutes_to_local_time(465) == time(7, 45)


def test_plan_helpers_read_vehicle_fields():
    plan = {"startTime": 1320, "timeConsuming": 480}
    assert plan_start_time(plan) == time(22, 0)
    assert plan_duration_hours(plan) == 8


def test_plan_helpers_reject_invalid():
    assert plan_start_time(None) is None
    assert plan_start_time({"startTime": 2000}) is None
    assert plan_duration_hours({"timeConsuming": 0}) is None
    assert plan_duration_hours({}) is None
