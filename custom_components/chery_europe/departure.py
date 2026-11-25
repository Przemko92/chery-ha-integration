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
from collections.abc import Iterable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

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

#: Minutes between the press of the quick departure button and putting the
#: previous plan back.
QUICK_DEPARTURE_MINUTES = 15

#: Spacing and budget of the retries when the car refuses the automatic restore
#: (asleep, command queue busy); after the last attempt the plan stays as it is
#: and the failure is logged.
RESTORE_RETRY_MINUTES = 5
RESTORE_MAX_ATTEMPTS = 3


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
    days: Iterable[int] | None = None,
) -> None:
    """Write the departure plan to the car, keeping every other plan.

    Setting a time while no departure plan exists and nothing is armed only
    stores a local draft: the time entity alone must not create a plan slot on
    the car. Turning the switch on creates the plan from that draft.

    ``days`` replaces the weekday list for this one write; when it is omitted
    the list the plan reports (or the last one commanded) is kept.
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
    plan_days = (
        departure_days(coordinator)
        if days is None
        else sorted({int(day) for day in days})
    )
    if not plan_days:
        raise HomeAssistantError("Select at least one weekday for the departure plan")
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
            days=plan_days,
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
    coordinator.departure_days = plan_days
    coordinator.invalidate_prepare_cache()
    coordinator.async_set_updated_data(
        apply_travel_appointment(data, updated, polled_at=datetime.now(UTC).isoformat())
    )
    coordinator.schedule_refresh_after_command()


def departure_snapshot(
    coordinator: CheryEuropeDataUpdateCoordinator,
) -> dict[str, Any]:
    """Return the departure parameters exactly as the car and HA hold them now."""
    travel_time, armed = departure_state(coordinator)
    return {
        "travel_time": travel_time,
        "days": list(departure_days(coordinator)),
        "enabled": bool(armed),
    }


async def async_restore_departure(
    coordinator: CheryEuropeDataUpdateCoordinator,
    entry: ConfigEntry,
) -> None:
    """Put the departure plan back to the parameters saved before a quick shift.

    The snapshot is consumed, so the restore runs once and a second press
    cannot walk the plan further back than the owner last set it.
    """
    previous = getattr(coordinator, "departure_previous", None)
    if not previous:
        raise HomeAssistantError("There are no saved departure settings to restore")

    await async_set_departure(
        coordinator,
        entry,
        travel_time=previous.get("travel_time"),
        enabled=bool(previous.get("enabled")),
        days=previous.get("days"),
    )
    coordinator.departure_previous = None


def departure_restore_at(
    coordinator: CheryEuropeDataUpdateCoordinator,
) -> datetime | None:
    """Return when the saved plan is due back, or None when nothing is armed."""
    return getattr(coordinator, "departure_restore_at", None)


def departure_restore_at_iso(
    coordinator: CheryEuropeDataUpdateCoordinator,
) -> str | None:
    """Return the restore deadline as an ISO string for the state attributes."""
    deadline = departure_restore_at(coordinator)
    return deadline.isoformat() if deadline is not None else None


def async_cancel_departure_restore(
    coordinator: CheryEuropeDataUpdateCoordinator,
    *,
    keep_deadline: bool = False,
) -> None:
    """Drop a pending restore, e.g. when the owner presses the button again.

    ``keep_deadline`` is for an unload or a reload: the timer dies with the
    entity but the deadline has to stay in the state attributes so the restore
    can pick up where it left off.
    """
    handle = getattr(coordinator, "departure_restore_handle", None)
    coordinator.departure_restore_handle = None
    if handle is not None:
        handle()
    if not keep_deadline:
        coordinator.departure_restore_at = None


def schedule_departure_restore(
    coordinator: CheryEuropeDataUpdateCoordinator,
    entry: ConfigEntry,
    *,
    delay: float,
    attempt: int = 1,
) -> None:
    """Put the saved departure plan back once the quick departure has left.

    A quick departure is temporary by design: the plan the owner had is written
    back without another press, so a "leave in 15 minutes" press cannot leave
    the car prepared at a time nobody asked for.  A refused write (car asleep)
    is retried a few times before giving up.
    """
    async_cancel_departure_restore(coordinator)
    deadline = dt_util.utcnow() + timedelta(seconds=max(delay, 0))
    coordinator.departure_restore_at = deadline
    coordinator.departure_restore_attempt = attempt

    async def _restore(_now: datetime | None = None) -> None:
        coordinator.departure_restore_handle = None
        try:
            await async_restore_departure(coordinator, entry)
        except Exception as exc:  # noqa: BLE001 - the timer must not die loudly
            if attempt >= RESTORE_MAX_ATTEMPTS:
                _LOGGER.error(
                    "Could not put the departure plan back after the quick "
                    "departure: %s",
                    exc,
                )
                coordinator.departure_restore_at = None
                coordinator.departure_restore_attempt = 0
                return
            _LOGGER.warning(
                "Restoring the departure plan failed (%s); retrying in %s minutes",
                exc,
                RESTORE_RETRY_MINUTES,
            )
            schedule_departure_restore(
                coordinator,
                entry,
                delay=RESTORE_RETRY_MINUTES * 60,
                attempt=attempt + 1,
            )
            return
        coordinator.departure_restore_at = None
        coordinator.departure_restore_attempt = 0

    cancel: Callable[[], None] = async_call_later(
        coordinator.hass, max(delay, 0), _restore
    )
    coordinator.departure_restore_handle = cancel
