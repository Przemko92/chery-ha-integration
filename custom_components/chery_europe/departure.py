"""Departure-plan helpers shared by the ``time`` and ``switch`` platforms.

Two entities drive the same thing: the ``time`` entity "Godzina wyjazdu" holds
the departure time, and the ``switch`` entity "Wyjazd start" arms it. Both
write one managed plan
(:data:`~.prepare_plan.DEPARTURE_PLAN_NAME`) through the same call, and both
read their state back from the plan the car reports, so Home Assistant always
shows what the vehicle actually stored.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

from .const import TSP_CODE_ASLEEP
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import apply_travel_appointment
from .exceptions import CheryEuropeCommandError, CheryEuropeException
from .pin import resolve_pin
from .prepare_plan import (
    DEFAULT_DEPARTURE_DAYS,
    DEFAULT_DEPARTURE_TIME,
    DEPARTURE_PLAN_NAME,
    departure_plan_update,
    find_plan_by_name,
    normalize_travel_time,
)

_LOGGER = logging.getLogger(__name__)


def prepare_plans_of(data: Any) -> list[dict[str, Any]] | None:
    """Return the plan list the last poll reported, or None when unknown."""
    plans = getattr(data, "prepare_plans", None)
    return list(plans) if plans is not None else None


def departure_state(
    coordinator: CheryEuropeDataUpdateCoordinator,
) -> tuple[str, bool]:
    """Return the managed departure time and whether the plan is armed.

    The plans come from ``/asd/travelManage/travelQuery``, the same list the
    app shows, so the entities report what the car actually stored. While that
    read has not answered yet (or the plan is missing) the entity falls back to
    the last state Home Assistant commanded, kept on the coordinator and
    restored by the entities.
    """
    plans = prepare_plans_of(coordinator.data) or []
    plan = find_plan_by_name(plans, DEPARTURE_PLAN_NAME)
    travel_time = getattr(coordinator, "departure_draft", None) or DEFAULT_DEPARTURE_TIME
    if plan and plan.get("travel_time"):
        try:
            travel_time = normalize_travel_time(plan["travel_time"])
        except ValueError:
            pass
        return travel_time, bool(plan.get("enabled"))
    return travel_time, bool(getattr(coordinator, "departure_armed", None))


def departure_days(coordinator: CheryEuropeDataUpdateCoordinator) -> list[int]:
    """Return the weekdays the managed departure plan repeats on."""
    plans = prepare_plans_of(coordinator.data) or []
    plan = find_plan_by_name(plans, DEPARTURE_PLAN_NAME)
    if plan and plan.get("days"):
        return [int(day) for day in plan["days"]]
    stored_days = getattr(coordinator, "departure_days", None)
    if stored_days:
        return [int(day) for day in stored_days]
    return list(DEFAULT_DEPARTURE_DAYS)


async def async_set_departure_days(
    coordinator: CheryEuropeDataUpdateCoordinator,
    entry: ConfigEntry,
    *,
    add: Iterable[int] = (),
    remove: Iterable[int] = (),
) -> None:
    """Toggle weekdays of the managed departure plan and push the result.

    The weekday list is stored with the plan and reads back from the car; the
    coordinator copy is the fallback while that read has not answered. Removing
    the last remaining day is refused: a plan with no weekday means nothing to
    the vehicle.
    """
    current = departure_days(coordinator)
    dropped = {int(day) for day in remove}
    days = sorted({day for day in current if day not in dropped} | {int(day) for day in add})
    if not days:
        raise HomeAssistantError(
            "Select at least one weekday for the departure plan"
        )
    coordinator.departure_days = days
    try:
        await async_set_departure(coordinator, entry)
    except Exception:
        coordinator.departure_days = current
        raise


async def async_set_departure(
    coordinator: CheryEuropeDataUpdateCoordinator,
    entry: ConfigEntry,
    *,
    travel_time: str | None = None,
    enabled: bool | None = None,
) -> None:
    """Write the departure plan to the car, keeping every other plan.

    Setting a time while no departure plan exists and nothing is armed only
    stores a local draft: the time entity alone must not create a plan slot on
    the car. Turning the switch on creates the plan from that draft.
    """
    data = coordinator.data
    vin = getattr(data, "vin", None)
    if not vin:
        raise HomeAssistantError("The vehicle is not available")
    plans = prepare_plans_of(data)
    if plans is None:
        # The car replaces the whole list, so a list we have not read could
        # wipe the owner's other plans.
        raise HomeAssistantError(
            "The vehicle's preparation plans are unknown; retry after the next poll"
        )

    current_time, current_enabled = departure_state(coordinator)
    new_time = normalize_travel_time(travel_time or current_time)
    new_enabled = current_enabled if enabled is None else bool(enabled)
    plan_exists = find_plan_by_name(plans, DEPARTURE_PLAN_NAME) is not None

    if not plan_exists and not new_enabled:
        coordinator.departure_draft = new_time
        coordinator.departure_armed = False
        return

    try:
        updated = departure_plan_update(
            plans,
            new_time,
            enabled=new_enabled,
            days=departure_days(coordinator),
        )
    except ValueError as exc:
        raise HomeAssistantError(f"Cannot schedule the departure: {exc}") from exc

    pin = resolve_pin(entry, None)
    permissions = (
        coordinator.permissions
        if getattr(coordinator, "_permissions_loaded", False)
        else None
    )
    try:
        response = await coordinator.api.send_travel_appointment(
            vin, pin, updated, permissions
        )
    except CheryEuropeException as exc:
        raise HomeAssistantError(
            f"Chery Europe preparation command failed: {exc}"
        ) from exc
    if not response.get("ok"):
        code = response.get("code")
        if code == TSP_CODE_ASLEEP:
            raise CheryEuropeCommandError(
                "Chery Europe preparation command failed: the car is asleep; "
                "wake it (open the app or unlock the car) and retry"
            )
        message = response.get("message") or code
        raise CheryEuropeCommandError(
            f"Chery Europe preparation command failed: {message}"
        )

    coordinator.departure_draft = new_time
    coordinator.departure_armed = new_enabled
    coordinator.departure_days = departure_days(coordinator)
    coordinator.invalidate_prepare_cache()
    coordinator.async_set_updated_data(
        apply_travel_appointment(data, updated, polled_at=datetime.now(UTC).isoformat())
    )
    coordinator.schedule_refresh_after_command()
