"""Helpers for scheduled charging times.

Chery stores ``startTime`` as minutes from midnight in **local** wall-clock
time (not UTC). Measured on the related Omoda/Jaecoo stack: writing
``startTime = 0`` shows 00:00 in the official app (would be 02:00 CEST if the
wire were UTC).
"""

from __future__ import annotations

from datetime import time
from typing import Any


def local_time_to_minutes(value: time) -> int:
    """Convert a local wall-clock time to minutes from midnight."""
    return int(value.hour) * 60 + int(value.minute)


def minutes_to_local_time(minutes: int) -> time:
    """Convert minutes from midnight to a local wall-clock time."""
    minutes = int(minutes) % 1440
    return time(hour=minutes // 60, minute=minutes % 60)


def format_minutes_as_hhmm(minutes: int) -> str:
    """Format schedule minutes as HH:MM."""
    local = minutes_to_local_time(minutes)
    return f"{local.hour:02d}:{local.minute:02d}"


def plan_start_time(plan: dict[str, Any] | None) -> time | None:
    """Return the plan start time, or None if missing/invalid."""
    if not isinstance(plan, dict):
        return None
    try:
        minutes = int(plan["startTime"])
    except (KeyError, TypeError, ValueError):
        return None
    if not 0 <= minutes < 1440:
        return None
    return minutes_to_local_time(minutes)


def plan_duration_hours(plan: dict[str, Any] | None) -> int | None:
    """Return the plan duration in whole hours, or None if missing/invalid."""
    if not isinstance(plan, dict):
        return None
    try:
        minutes = int(plan["timeConsuming"])
    except (KeyError, TypeError, ValueError):
        return None
    if minutes <= 0:
        return None
    hours = max(1, round(minutes / 60))
    return hours


# Backwards-compatible aliases (minutes are local, not UTC).
local_time_to_utc_minutes = local_time_to_minutes
utc_minutes_to_local_time = minutes_to_local_time
format_utc_minutes_as_local = format_minutes_as_hhmm
