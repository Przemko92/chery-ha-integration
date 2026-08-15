# pyright: reportArgumentType=false
"""Tests for UTC ↔ local charge schedule conversion."""

from datetime import datetime, time, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.charge_schedule import (
    format_utc_minutes_as_local,
    local_time_to_utc_minutes,
    utc_minutes_to_local_time,
)

WARSAW = ZoneInfo("Europe/Warsaw")


def test_local_10_cest_converts_to_utc_480():
    """10:00 CEST is 08:00 UTC (480 minutes)."""
    local_now = datetime(2026, 8, 15, 12, 0, tzinfo=WARSAW)

    with (
        patch(
            "custom_components.chery_europe.charge_schedule.dt_util.now",
            return_value=local_now,
        ),
        patch(
            "custom_components.chery_europe.charge_schedule.dt_util.as_utc",
            side_effect=lambda dt: dt.astimezone(timezone.utc),
        ),
    ):
        assert local_time_to_utc_minutes(time(10, 0)) == 480


def test_utc_480_converts_to_local_10_cest():
    """08:00 UTC displays as 10:00 in Europe/Warsaw (summer)."""
    utc_now = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)

    with (
        patch(
            "custom_components.chery_europe.charge_schedule.dt_util.utcnow",
            return_value=utc_now,
        ),
        patch(
            "custom_components.chery_europe.charge_schedule.dt_util.as_local",
            side_effect=lambda dt: dt.astimezone(WARSAW),
        ),
    ):
        assert utc_minutes_to_local_time(480) == time(10, 0)
        assert format_utc_minutes_as_local(480) == "10:00"


def test_local_23_cest_converts_to_utc_1260():
    """23:00 CEST is 21:00 UTC (1260 minutes)."""
    local_now = datetime(2026, 8, 15, 12, 0, tzinfo=WARSAW)

    with (
        patch(
            "custom_components.chery_europe.charge_schedule.dt_util.now",
            return_value=local_now,
        ),
        patch(
            "custom_components.chery_europe.charge_schedule.dt_util.as_utc",
            side_effect=lambda dt: dt.astimezone(timezone.utc),
        ),
    ):
        assert local_time_to_utc_minutes(time(23, 0)) == 1260
