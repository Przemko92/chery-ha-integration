"""Scheduled cabin/battery preparation ("prepare car") plans.

The official Chery Europe app lets the owner schedule a departure time; the
car then pre-conditions the cabin and can warm the traction battery before
that time. This module holds the pure plan logic — normalisation, validation,
merging and the next-departure calculation — so it can be tested without Home
Assistant and reused by both the coordinator and the services.

A *plan* is a plain ``dict`` in the shape produced by :func:`build_plan` and
:func:`parse_plan`:

.. code-block:: python

    {
        "plan_id": "1234567890",      # None for a plan that was never saved
        "name": "Work",               # at most 10 characters, unique
        "travel_time": "07:30",       # local wall-clock HH:MM
        "days": [1, 2, 3, 4, 5],      # ISO weekday numbers, 1 = Monday
        "enabled": True,              # switchStatus
        "temperature": "22.0",        # target cabin temperature, or None
        "features": {
            "battery_heat": True,
            "steering_wheel_heat": False,
            "driver_seat_heat": False,
            "front_defrost": False,
            "rear_defrost": False,
        },
    }

Field names on the wire (``preparePlans`` entries) are the ones the app uses
for the matching vehicle-control commands; they are kept in
:data:`PREPARE_FEATURE_FIELDS` so a wrong guess is a one-line fix.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any

REPEAT_DAILY = "daily"
REPEAT_WORKDAYS = "workdays"
REPEAT_WEEKEND = "weekend"
REPEAT_CUSTOM = "custom"
REPEAT_MODES = (REPEAT_DAILY, REPEAT_WORKDAYS, REPEAT_WEEKEND, REPEAT_CUSTOM)

ALL_DAYS: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7)
WORKDAYS: tuple[int, ...] = (1, 2, 3, 4, 5)
WEEKEND: tuple[int, ...] = (6, 7)

MAX_PLANS = 5
MAX_NAME_LENGTH = 10
MIN_GAP_MINUTES = 20
MIN_TEMPERATURE = 16.0
MAX_TEMPERATURE = 32.0

FEATURE_KEYS: tuple[str, ...] = (
    "battery_heat",
    "steering_wheel_heat",
    "driver_seat_heat",
    "front_defrost",
    "rear_defrost",
)

#: Plan field -> vehicle-control body key. ``value`` is what to send when the
#: feature is on; features that are off are omitted from the body.
PREPARE_FEATURE_FIELDS: dict[str, str] = {
    "battery_heat": "batteryPackHeat",
    "steering_wheel_heat": "steerWheelHeatSwitch",
    "driver_seat_heat": "pSeatHeating",
    "front_defrost": "frontDefrosting",
    "rear_defrost": "backDefrosting",
}

#: Value sent for an enabled feature. Seat heating uses a level, the rest a flag.
PREPARE_FEATURE_VALUES: dict[str, str] = {
    "battery_heat": "1",
    "steering_wheel_heat": "1",
    "driver_seat_heat": "3",
    "front_defrost": "1",
    "rear_defrost": "1",
}

#: Response keys that may carry the plan list, most specific first.
PREPARE_LIST_KEYS: tuple[str, ...] = (
    "preparePlans",
    "prepare_plans",
    "travelAppointPlans",
    "travelPlans",
)


def normalize_days(repeat: str, days: Sequence[int] | None = None) -> list[int]:
    """Return the ISO weekday list for a repeat mode.

    ``custom`` requires at least one explicit day.
    """
    mode = (repeat or REPEAT_DAILY).strip().lower()
    if mode == REPEAT_DAILY:
        return list(ALL_DAYS)
    if mode == REPEAT_WORKDAYS:
        return list(WORKDAYS)
    if mode == REPEAT_WEEKEND:
        return list(WEEKEND)
    if mode != REPEAT_CUSTOM:
        raise ValueError(f"Unknown repeat mode: {repeat}")

    if not days:
        raise ValueError("repeat 'custom' needs at least one day in 'days'")
    picked: set[int] = set()
    for raw in days:
        try:
            day = int(raw)
        except (TypeError, ValueError) as err:
            raise ValueError(f"Invalid day: {raw}") from err
        if day < 1 or day > 7:
            raise ValueError(f"Day out of range 1-7: {day}")
        picked.add(day)
    return sorted(picked)


def normalize_temperature(value: Any) -> str | None:
    """Return the cabin temperature as ``"22.0"``, or None when unset."""
    if value in (None, ""):
        return None
    try:
        temperature = float(value)
    except (TypeError, ValueError) as err:
        raise ValueError(f"Invalid temperature: {value}") from err
    if not MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE:
        raise ValueError(
            f"Temperature must be between {MIN_TEMPERATURE:.0f} and "
            f"{MAX_TEMPERATURE:.0f} \u00b0C"
        )
    return f"{temperature:.1f}"


def normalize_travel_time(value: Any) -> str:
    """Return a travel time as ``HH:MM``."""
    if isinstance(value, datetime):  # pragma: no cover - defensive
        return f"{value.hour:02d}:{value.minute:02d}"
    text = str(value or "").strip()
    if not text:
        raise ValueError("travel_time is required")
    if ":" in text:
        hours, _, minutes = text.partition(":")
    elif len(text) == 4 and text.isdigit():
        hours, minutes = text[:2], text[2:]
    else:
        raise ValueError(f"Invalid travel_time: {value}")
    try:
        hour = int(hours) % 24
        minute = int(minutes) % 60
    except (TypeError, ValueError) as err:
        raise ValueError(f"Invalid travel_time: {value}") from err
    return f"{hour:02d}:{minute:02d}"


def travel_minutes(travel_time: str) -> int:
    """Return minutes from midnight for an ``HH:MM`` string."""
    hours, _, minutes = normalize_travel_time(travel_time).partition(":")
    return int(hours) * 60 + int(minutes)


def normalize_name(value: Any) -> str:
    """Return a trimmed plan name within the car's 10-character limit."""
    name = str(value or "").strip()
    if not name:
        raise ValueError("plan_name is required")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(
            f"plan_name must be at most {MAX_NAME_LENGTH} characters"
        )
    return name


def build_plan(
    *,
    name: Any,
    travel_time: Any,
    repeat: str = REPEAT_DAILY,
    days: Sequence[int] | None = None,
    enabled: bool = True,
    temperature: Any = None,
    battery_heat: bool = False,
    steering_wheel_heat: bool = False,
    driver_seat_heat: bool = False,
    front_defrost: bool = False,
    rear_defrost: bool = False,
    plan_id: Any = None,
) -> dict[str, Any]:
    """Return a normalised plan dict from service input."""
    plan = {
        "plan_id": str(plan_id) if plan_id not in (None, "") else None,
        "name": normalize_name(name),
        "travel_time": normalize_travel_time(travel_time),
        "days": normalize_days(repeat, days),
        "enabled": bool(enabled),
        "temperature": normalize_temperature(temperature),
        "features": {
            "battery_heat": bool(battery_heat),
            "steering_wheel_heat": bool(steering_wheel_heat),
            "driver_seat_heat": bool(driver_seat_heat),
            "front_defrost": bool(front_defrost),
            "rear_defrost": bool(rear_defrost),
        },
    }
    return plan


def validate_plans(
    plans: Iterable[dict[str, Any]], plan: dict[str, Any]
) -> None:
    """Raise ValueError when ``plan`` cannot be added to ``plans``.

    Mirrors the limits the car and the app enforce: at most five plans, unique
    names, and departures at least 20 minutes apart.
    """
    entries = list(plans)
    target_id = str(plan.get("plan_id") or "")
    # Replacing an existing plan must not be counted twice.
    replacing = bool(target_id) and any(
        str(existing.get("plan_id") or "") == target_id for existing in entries
    )
    others = [
        existing
        for existing in entries
        if not (replacing and str(existing.get("plan_id") or "") == target_id)
    ]
    active = [existing for existing in plans if _is_enabled(existing)]
    if plan.get("enabled") and not replacing and len(active) >= MAX_PLANS:
        raise ValueError(f"The car accepts at most {MAX_PLANS} plans")

    minutes = travel_minutes(plan["travel_time"])
    for existing in others:
        if existing.get("name") == plan["name"]:
            raise ValueError(f"A plan named {plan['name']} already exists")
        other_minutes = travel_minutes(
            existing.get("travel_time") or existing.get("travelTime") or "00:00"
        )
        if abs(other_minutes - minutes) < MIN_GAP_MINUTES:
            raise ValueError(
                "Departures must be at least "
                f"{MIN_GAP_MINUTES} minutes apart "
                f"({existing.get('name')} is at "
                f"{existing.get('travel_time')})"
            )


def merge_plan(
    plans: Iterable[dict[str, Any]], plan: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return the plan list with ``plan`` added or replacing the same id."""
    result = [dict(existing) for existing in plans]
    if plan.get("plan_id") not in (None, ""):
        for index, existing in enumerate(result):
            if str(existing.get("plan_id") or "") == str(plan["plan_id"]):
                result[index] = dict(plan)
                return result
    result.append(dict(plan))
    return result


def _optional_str(value: Any) -> str | None:
    """Return a trimmed string, or None when the value is empty."""
    if value in (None, ""):
        return None
    return str(value)


def disable_plan(plans: Iterable[dict[str, Any]], plan_id: Any) -> list[dict[str, Any]]:
    """Return the plan list with one plan switched off.

    The car insists a plan is deactivated before it can be deleted, so the
    integration never removes an entry — it clears ``enabled`` and renames the
    leftover so it can be reused later.
    """
    target = str(plan_id or "")
    if not target:
        raise ValueError("plan_id is required")
    result: list[dict[str, Any]] = []
    found = False
    for existing in plans:
        current = dict(existing)
        if str(current.get("plan_id") or "") == target:
            found = True
            current["enabled"] = False
            current["features"] = {
                key: False for key in current.get("features", {})
            }
        result.append(current)
    if not found:
        raise ValueError(f"Unknown plan_id: {plan_id}")
    return result


def next_departure(
    plans: Iterable[dict[str, Any]], now: datetime
) -> datetime | None:
    """Return the next enabled departure as a timezone-aware datetime."""
    best: datetime | None = None
    for plan in plans:
        if not _is_enabled(plan):
            continue
        candidate = next_run(plan, now)
        if candidate is None:
            continue
        if best is None or candidate < best:
            best = candidate
    return best


def next_run(plan: dict[str, Any], now: datetime) -> datetime | None:
    """Return the next occurrence of a single plan, honouring its weekdays."""
    try:
        minutes = travel_minutes(plan.get("travel_time") or "00:00")
    except ValueError:
        return None
    days = _plan_days(plan)
    if not days:
        return None
    for offset in range(8):
        day = (now + timedelta(days=offset)).replace(
            hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0
        )
        if day.isoweekday() not in days:
            continue
        if day <= now:
            continue
        return day
    return None


def parse_plan(raw: Any) -> dict[str, Any] | None:
    """Return a normalised plan from a ``preparePlans`` entry, or None."""
    if not isinstance(raw, dict):
        return None
    travel_time = raw.get("travelTime") or raw.get("travel_time")
    name = raw.get("planName") or raw.get("plan_name") or raw.get("name")
    if travel_time in (None, ""):
        return None
    try:
        normalized_time = normalize_travel_time(travel_time)
    except ValueError:
        normalized_time = None
    if normalized_time is None:
        return None
    features = {key: _flag(raw.get(PREPARE_FEATURE_FIELDS[key])) for key in FEATURE_KEYS}
    return {
        "plan_id": _optional_str(raw.get("planId") or raw.get("plan_id")),
        "name": str(name or "?"),
        "travel_time": normalized_time,
        "days": _plan_days(raw) or list(ALL_DAYS),
        "enabled": _is_enabled(raw),
        "temperature": _optional_str(raw.get("temperature")),
        "features": features,
    }


def parse_plans(payload: Any) -> list[dict[str, Any]] | None:
    """Return the plan list from a travelAppointQuery payload, or None.

    ``None`` means the payload carried no recognisable plan list, so the
    coordinator keeps the last known one instead of clearing it.
    """
    if not isinstance(payload, dict):
        return None
    # tspconsole wraps query results in "body" (prepareQuery), some endpoints
    # in "data" - unwrap whichever is present before looking for the list.
    data: Any = payload
    for wrapper in ("body", "data"):
        nested = data.get(wrapper)
        if isinstance(nested, (dict, list)):
            data = nested
            break
    if isinstance(data, dict):
        for key in PREPARE_LIST_KEYS:
            if key in data:
                data = data[key]
                break
        else:
            # A single plan object without a wrapper list.
            if any(key in data for key in ("travelTime", "planName")):
                plan = parse_plan(data)
                return [plan] if plan else None
            return None
    if not isinstance(data, list):
        return None
    plans = [plan for plan in (parse_plan(item) for item in data) if plan]
    return plans


def _plan_days(plan: dict[str, Any]) -> list[int]:
    raw = plan.get("days", plan.get("cycleData"))
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        raw = [chunk for chunk in raw.replace(" ", "").split(",") if chunk]
    days: list[int] = []
    for item in raw:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 7 and day not in days:
            days.append(day)
    return sorted(days)


def _is_enabled(plan: dict[str, Any]) -> bool:
    if "enabled" in plan:
        return bool(plan["enabled"])
    return str(plan.get("switchStatus")) == "1"


def _flag(value: Any) -> bool:
    """Return whether a body value means "on" (``"0"``/False/None mean off)."""
    if value in (None, ""):
        return False
    if isinstance(value, bool):
        return value
    return str(value) not in {"0", "false", "False", "None"}
