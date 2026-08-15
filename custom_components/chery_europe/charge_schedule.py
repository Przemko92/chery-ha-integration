"""Helpers for scheduled charging times.

Chery stores ``startTime`` as minutes from midnight in UTC. Home Assistant
exposes local wall-clock times, so convert at the integration boundary.
"""

from __future__ import annotations

from datetime import time, timedelta

from homeassistant.util import dt as dt_util


def local_time_to_utc_minutes(value: time) -> int:
    """Convert a local wall-clock time to UTC minutes from midnight."""
    local_now = dt_util.now()
    local_dt = local_now.replace(
        hour=value.hour, minute=value.minute, second=0, microsecond=0
    )
    utc_dt = dt_util.as_utc(local_dt)
    return utc_dt.hour * 60 + utc_dt.minute


def utc_minutes_to_local_time(minutes: int) -> time:
    """Convert UTC minutes from midnight to a local wall-clock time."""
    minutes = int(minutes) % 1440
    utc_now = dt_util.utcnow()
    utc_dt = utc_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
        minutes=minutes
    )
    local_dt = dt_util.as_local(utc_dt)
    return time(hour=local_dt.hour, minute=local_dt.minute)


def format_utc_minutes_as_local(minutes: int) -> str:
    """Format UTC schedule minutes as HH:MM in the Home Assistant local zone."""
    local = utc_minutes_to_local_time(minutes)
    return f"{local.hour:02d}:{local.minute:02d}"
