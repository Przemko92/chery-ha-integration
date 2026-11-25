"""Helpers for scheduled charging times.

The car stores ``startTime`` and ``endTime`` as minutes from midnight in UTC
and shows them in the local time zone. A local 11:00 in Poland (UTC+2) must
go out as 09:00, otherwise the car displays 13:00. ``timeConsuming`` is a
duration in minutes and is not shifted.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any

from homeassistant.util import dt as dt_util


def local_time_to_minutes(value: time) -> int:
    """Convert a local wall-clock time to minutes from midnight."""
    return int(value.hour) * 60 + int(value.minute)


def minutes_to_local_time(minutes: int) -> time:
    """Convert minutes from midnight to a clock time, without a zone shift."""
    minutes = int(minutes) % 1440
    return time(hour=minutes // 60, minute=minutes % 60)


def format_minutes_as_hhmm(minutes: int) -> str:
    """Format clock minutes as HH:MM, without a zone shift."""
    local = minutes_to_local_time(minutes)
    return f"{local.hour:02d}:{local.minute:02d}"


def local_minutes_to_utc(minutes: int) -> int:
    """Convert local minutes-from-midnight to the UTC minutes the car stores."""
    minutes = int(minutes) % 1440
    local = dt_util.now().replace(
        hour=minutes // 60,
        minute=minutes % 60,
        second=0,
        microsecond=0,
    )
    utc = dt_util.as_utc(local)
    return utc.hour * 60 + utc.minute


def utc_minutes_to_local(minutes: int) -> int:
    """Convert the car's UTC minutes-from-midnight to local minutes."""
    minutes = int(minutes) % 1440
    utc = datetime.now(timezone.utc).replace(
        hour=minutes // 60,
        minute=minutes % 60,
        second=0,
        microsecond=0,
    )
    local = dt_util.as_local(utc)
    return local.hour * 60 + local.minute


def plan_start_time(plan: dict[str, Any] | None) -> time | None:
    """Return the plan start as a local wall-clock time."""
    if not isinstance(plan, dict):
        return None
    try:
        minutes = int(plan["startTime"])
    except (KeyError, TypeError, ValueError):
        return None
    if not 0 <= minutes < 1440:
        return None
    return minutes_to_local_time(utc_minutes_to_local(minutes))


CHARGE_DURATION_STEP_MINUTES = 15
CHARGE_DURATION_MIN_MINUTES = 60
CHARGE_DURATION_MAX_MINUTES = 24 * 60


def snap_duration_minutes(minutes: Any) -> int:
    """Clamp a duration to the 15 minute grid the car accepts, 1 h .. 24 h."""
    try:
        value = int(round(float(minutes) / CHARGE_DURATION_STEP_MINUTES))
    except (TypeError, ValueError):
        value = CHARGE_DURATION_MIN_MINUTES // CHARGE_DURATION_STEP_MINUTES
    value *= CHARGE_DURATION_STEP_MINUTES
    return max(CHARGE_DURATION_MIN_MINUTES, min(CHARGE_DURATION_MAX_MINUTES, value))


def window_minutes(start_minutes: int, duration_minutes: int) -> tuple[int, bool]:
    """Return the end clock minutes of a window and whether it ends tomorrow.

    A window that runs past midnight wraps around: a start at 22:00 with six
    hours gives 04:00 on the next day, and the flag says so.
    """
    total = (int(start_minutes) % 1440) + int(duration_minutes)
    return total % 1440, total >= 1440


def duration_for_end(start_minutes: int, end_minutes: int) -> int:
    """Return the duration that ends at ``end_minutes`` for a given start.

    The end is read as the next occurrence of that clock time, so an end that
    is not after the start lands on the following day. A start and an end that
    are the same clock time mean a full 24 hour window.
    """
    minutes = (int(end_minutes) - int(start_minutes)) % 1440
    if minutes == 0:
        minutes = CHARGE_DURATION_MAX_MINUTES
    return snap_duration_minutes(minutes)


def plan_duration_minutes(plan: dict[str, Any] | None) -> int | None:
    """Return the plan duration in minutes on the 15 minute grid."""
    if not isinstance(plan, dict):
        return None
    minutes = _duration_minutes(plan)
    if minutes is None or minutes <= 0:
        return None
    return snap_duration_minutes(minutes)


def plan_duration_hours(plan: dict[str, Any] | None) -> float | None:
    """Return the plan duration in hours, in 0.25 h steps.

    Prefer ``timeConsuming`` when the plan says the duration was set.
    Otherwise derive it from ``endTime - startTime``, which is how the car
    shows a window when only an end clock time was stored.
    """
    minutes = plan_duration_minutes(plan)
    if minutes is None:
        return None
    return minutes / 60


def _duration_minutes(plan: dict[str, Any]) -> int | None:
    flag = plan.get("hasSetTimeConsuming")
    duration_set = flag is None or str(flag) not in {"0", "false", "False"}
    if duration_set:
        try:
            return int(plan["timeConsuming"])
        except (KeyError, TypeError, ValueError):
            pass
    try:
        start = int(plan["startTime"]) % 1440
        end = int(plan["endTime"]) % 1440
    except (KeyError, TypeError, ValueError):
        return None
    return (end - start) % 1440
