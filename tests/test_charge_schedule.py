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
    plan = {"startTime": 1320, "timeConsuming": 480, "hasSetTimeConsuming": 1}
    assert plan_start_time(plan) == time(22, 0)
    assert plan_duration_hours(plan) == 8


def test_plan_duration_from_end_time_when_duration_was_not_set():
    plan = {"startTime": 600, "endTime": 840, "hasSetTimeConsuming": 0}
    assert plan_duration_hours(plan) == 4


def test_local_eleven_is_shifted_by_the_local_offset():
    import datetime
    from zoneinfo import ZoneInfo

    from homeassistant.util import dt as dt_util

    from custom_components.chery_europe.charge_schedule import (
        local_minutes_to_utc,
        utc_minutes_to_local,
    )

    zone = ZoneInfo("Europe/Warsaw")
    dt_util.set_default_time_zone(zone)
    try:
        # 22 Sep 2026 is CEST: local 11:00 is stored as 09:00, which is why the
        # car was showing 13:00 when 11:00 was sent unchanged.
        summer = datetime.datetime(2026, 9, 22, 11, 0, tzinfo=zone)
        assert summer.utcoffset() == datetime.timedelta(hours=2)

        local_minutes = 11 * 60
        offset = datetime.datetime.now(zone).utcoffset()
        assert offset is not None
        expected = (local_minutes - int(offset.total_seconds() // 60)) % 1440
        wire = local_minutes_to_utc(local_minutes)
        assert wire == expected
        assert utc_minutes_to_local(wire) == local_minutes
        assert plan_start_time({"startTime": wire}) == time(11, 0)
    finally:
        dt_util.set_default_time_zone(datetime.UTC)


def test_plan_helpers_reject_invalid():
    assert plan_start_time(None) is None
    assert plan_start_time({"startTime": 2000}) is None
    assert plan_duration_hours({"timeConsuming": 0}) is None
    assert plan_duration_hours({}) is None
