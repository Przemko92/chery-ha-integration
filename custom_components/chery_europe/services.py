"""Services for the Chery Europe integration."""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .charge_schedule import local_time_to_minutes
from .command_exec import async_send_vehicle_command
from .const import (
    ATTR_BATTERY_HEAT,
    ATTR_COMMAND_ID,
    ATTR_DAYS,
    ATTR_DRIVER_SEAT_HEAT,
    ATTR_DRY_RUN,
    ATTR_DURATION_HOURS,
    ATTR_ENABLED,
    ATTR_FRONT_DEFROST,
    ATTR_PAGE,
    ATTR_PAGE_SIZE,
    ATTR_PIN,
    ATTR_PLAN_ID,
    ATTR_PLAN_NAME,
    ATTR_REAR_DEFROST,
    ATTR_REPEAT,
    ATTR_START_TIME,
    ATTR_STEERING_WHEEL_HEAT,
    ATTR_TEMPERATURE,
    ATTR_TRAVEL_TIME,
    ATTR_UNREAD_ONLY,
    ATTR_VIN,
    DOMAIN,
    SERVICE_CANCEL_PREPARE_PLAN,
    SERVICE_GET_MESSAGES,
    SERVICE_LIST_PREPARE_PLANS,
    SERVICE_SEND_COMMAND,
    SERVICE_SET_PREPARE_PLAN,
    SERVICE_SET_SCHEDULED_CHARGING,
)
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import apply_command_feedback, apply_travel_appointment
from .exceptions import CheryEuropeCommandError, CheryEuropeException
from .pin import resolve_pin
from .prepare_plan import (
    REPEAT_MODES,
    build_plan,
    disable_plan,
    merge_plan,
    validate_plans,
)

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_VIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Required(ATTR_COMMAND_ID): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_PIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("temperature"): vol.Coerce(float),
        vol.Optional(ATTR_ENABLED): cv.boolean,
        vol.Optional("hvac_mode"): cv.string,
        vol.Optional("action"): cv.string,
        vol.Optional("seat_field"): cv.string,
        vol.Optional("level"): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
        vol.Optional("start_minutes"): vol.Coerce(int),
        vol.Optional(ATTR_DURATION_HOURS): vol.Coerce(int),
    }
)

SET_SCHEDULED_CHARGING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_START_TIME): cv.time,
        vol.Required(ATTR_DURATION_HOURS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=12)
        ),
        vol.Optional(ATTR_ENABLED, default=True): cv.boolean,
        vol.Optional(ATTR_PIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_VIN): vol.All(cv.string, vol.Length(min=1)),
    }
)

SET_PREPARE_PLAN_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PLAN_NAME): vol.All(cv.string, vol.Length(min=1, max=10)),
        vol.Required(ATTR_TRAVEL_TIME): cv.string,
        vol.Optional(ATTR_REPEAT, default="daily"): vol.In(REPEAT_MODES),
        vol.Optional(ATTR_DAYS): vol.All(cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=1, max=7))]),
        vol.Optional(ATTR_ENABLED, default=True): cv.boolean,
        vol.Optional(ATTR_TEMPERATURE): vol.All(vol.Coerce(float), vol.Range(min=16, max=32)),
        vol.Optional(ATTR_BATTERY_HEAT, default=False): cv.boolean,
        vol.Optional(ATTR_STEERING_WHEEL_HEAT, default=False): cv.boolean,
        vol.Optional(ATTR_DRIVER_SEAT_HEAT, default=False): cv.boolean,
        vol.Optional(ATTR_FRONT_DEFROST, default=False): cv.boolean,
        vol.Optional(ATTR_REAR_DEFROST, default=False): cv.boolean,
        vol.Optional(ATTR_PLAN_ID): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_DRY_RUN, default=False): cv.boolean,
        vol.Optional(ATTR_PIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_VIN): vol.All(cv.string, vol.Length(min=1)),
    }
)

CANCEL_PREPARE_PLAN_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_PLAN_ID): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_DRY_RUN, default=False): cv.boolean,
        vol.Optional(ATTR_PIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_VIN): vol.All(cv.string, vol.Length(min=1)),
    }
)

LIST_PREPARE_PLANS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_VIN): vol.All(cv.string, vol.Length(min=1)),
    }
)

GET_MESSAGES_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_VIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_PAGE, default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1)
        ),
        vol.Optional(ATTR_PAGE_SIZE, default=50): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=500)
        ),
        vol.Optional(ATTR_UNREAD_ONLY, default=False): cv.boolean,
    }
)

_LOGGER = logging.getLogger(__name__)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register Chery Europe services."""

    async def handle_send_command(call: ServiceCall) -> dict[str, Any]:
        entry = _get_loaded_entry(hass)
        coordinator = _coordinator_for_call(entry, call.data.get(ATTR_VIN))
        pin = resolve_pin(entry, call.data)
        vin = coordinator.data.vin if coordinator.data is not None else None
        if not vin:
            raise HomeAssistantError("Vehicle is unavailable")
        try:
            send_kwargs: dict[str, Any] = {
                "action": call.data.get("action"),
                "temperature": call.data.get("temperature"),
                "enabled": call.data.get(ATTR_ENABLED),
                "hvac_mode": call.data.get("hvac_mode"),
                "seat_field": call.data.get("seat_field"),
                "level": call.data.get("level"),
                "start_minutes": call.data.get("start_minutes"),
                "duration_hours": call.data.get(ATTR_DURATION_HOURS),
            }
            if getattr(coordinator, "_permissions_loaded", False):
                send_kwargs["permissions"] = coordinator.permissions
            response = await coordinator.api.send_command(
                vin,
                call.data[ATTR_COMMAND_ID],
                pin,
                **send_kwargs,
            )

            if not response.get("ok"):
                message = response.get("message") or response.get("code")
                raise CheryEuropeCommandError(
                    f"Chery Europe command failed: {message}"
                )

            if coordinator.data is not None:
                coordinator.async_set_updated_data(
                    apply_command_feedback(
                        coordinator.data,
                        call.data[ATTR_COMMAND_ID],
                        action=call.data.get("action"),
                        enabled=call.data.get(ATTR_ENABLED),
                        seat_field=call.data.get("seat_field"),
                        level=call.data.get("level"),
                        start_minutes=call.data.get("start_minutes"),
                        duration_hours=call.data.get(ATTR_DURATION_HOURS),
                    )
                )

            if hasattr(coordinator, "_update_status"):
                coordinator._update_status(
                    command_status=f"Command sent ✅ ({call.data[ATTR_COMMAND_ID]})"
                )
            coordinator.schedule_refresh_after_command()
        except HomeAssistantError:
            raise
        except CheryEuropeException as exc:
            if hasattr(coordinator, "_update_status"):
                coordinator._update_status(command_status=f"Command failed ❌: {exc}")
            raise
        except Exception as err:  # noqa: BLE001
            if hasattr(coordinator, "_update_status"):
                coordinator._update_status(command_status="Command failed ❌: network error")
            _LOGGER.exception("Unexpected Chery Europe command failure")
            raise HomeAssistantError("Failed to send Chery Europe command") from err
        return {"success": True}

    async def handle_set_scheduled_charging(call: ServiceCall) -> dict[str, Any]:
        entry = _get_loaded_entry(hass)
        coordinator = _coordinator_for_call(entry, call.data.get(ATTR_VIN))
        start: time = call.data[ATTR_START_TIME]
        duration_hours: int = call.data[ATTR_DURATION_HOURS]
        enabled: bool = call.data[ATTR_ENABLED]
        # Service start_time and the vehicle API both use local minutes from midnight.
        start_minutes = local_time_to_minutes(start)

        vin = coordinator.data.vin if coordinator.data is not None else None
        coordinator.charge_start_minutes = start_minutes
        coordinator.charge_duration_hours = duration_hours

        await async_send_vehicle_command(
            coordinator,
            entry,
            vin,
            {ATTR_PIN: call.data[ATTR_PIN]} if ATTR_PIN in call.data else {},
            command_id="ve_1202",
            enabled=enabled,
            start_minutes=start_minutes,
            duration_hours=duration_hours,
        )
        return {
            "success": True,
            "start_time": start.strftime("%H:%M"),
            "duration_hours": duration_hours,
            "enabled": enabled,
        }

    async def handle_set_prepare_plan(call: ServiceCall) -> dict[str, Any]:
        entry = _get_loaded_entry(hass)
        coordinator = _coordinator_for_call(entry, call.data.get(ATTR_VIN))
        vin = coordinator.data.vin if coordinator.data is not None else None
        if not vin:
            raise HomeAssistantError("Vehicle is unavailable")
        current = list(
            (coordinator.data.prepare_plans if coordinator.data is not None else None)
            or []
        )
        plan_id = call.data.get(ATTR_PLAN_ID)
        try:
            if plan_id and not any(
                str(plan.get("plan_id") or "") == str(plan_id) for plan in current
            ):
                raise ValueError(f"Unknown plan_id: {plan_id}")
            plan = build_plan(
                name=call.data[ATTR_PLAN_NAME],
                travel_time=call.data[ATTR_TRAVEL_TIME],
                repeat=call.data[ATTR_REPEAT],
                days=call.data.get(ATTR_DAYS),
                enabled=call.data[ATTR_ENABLED],
                temperature=call.data.get(ATTR_TEMPERATURE),
                battery_heat=call.data[ATTR_BATTERY_HEAT],
                steering_wheel_heat=call.data[ATTR_STEERING_WHEEL_HEAT],
                driver_seat_heat=call.data[ATTR_DRIVER_SEAT_HEAT],
                front_defrost=call.data[ATTR_FRONT_DEFROST],
                rear_defrost=call.data[ATTR_REAR_DEFROST],
                plan_id=plan_id,
            )
            validate_plans(current, plan)
            plans = merge_plan(current, plan)
        except ValueError as err:
            raise HomeAssistantError(f"Invalid preparation plan: {err}") from err

        if call.data[ATTR_DRY_RUN]:
            return {
                "success": True,
                "dry_run": True,
                "plans": plans,
                "body": _prepare_body(plans),
            }
        response = await _write_prepare_plans(coordinator, entry, vin, plans, call)
        return {"success": True, "plans": plans, "response": response}

    async def handle_cancel_prepare_plan(call: ServiceCall) -> dict[str, Any]:
        entry = _get_loaded_entry(hass)
        coordinator = _coordinator_for_call(entry, call.data.get(ATTR_VIN))
        vin = coordinator.data.vin if coordinator.data is not None else None
        if not vin:
            raise HomeAssistantError("Vehicle is unavailable")
        current = list(
            (coordinator.data.prepare_plans if coordinator.data is not None else None)
            or []
        )
        try:
            plans = disable_plan(current, call.data[ATTR_PLAN_ID])
        except ValueError as err:
            raise HomeAssistantError(f"Invalid preparation plan: {err}") from err

        if call.data[ATTR_DRY_RUN]:
            return {
                "success": True,
                "dry_run": True,
                "plans": plans,
                "body": _prepare_body(plans),
            }
        response = await _write_prepare_plans(coordinator, entry, vin, plans, call)
        return {"success": True, "plans": plans, "response": response}

    async def handle_list_prepare_plans(call: ServiceCall) -> dict[str, Any]:
        entry = _get_loaded_entry(hass)
        coordinator = _coordinator_for_call(entry, call.data.get(ATTR_VIN))
        vin = coordinator.data.vin if coordinator.data is not None else None
        if not vin:
            raise HomeAssistantError("Vehicle is unavailable")
        plans = await coordinator.api.query_travel_appointment(vin)
        if plans is None:
            return {
                "success": False,
                "message": "The car did not return its preparation plans",
                "plans": (
                    coordinator.data.prepare_plans
                    if coordinator.data is not None
                    else None
                ),
            }
        coordinator.invalidate_prepare_cache()
        if coordinator.data is not None:
            coordinator.async_set_updated_data(
                apply_travel_appointment(
                    coordinator.data,
                    plans,
                    polled_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        return {
            "success": True,
            "plans": plans,
            "next_departure": (
                coordinator.data.prepare_next_departure
                if coordinator.data is not None
                else None
            ),
        }

    async def _write_prepare_plans(
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
        vin: str,
        plans: list[dict[str, Any]],
        call: ServiceCall,
    ) -> dict[str, Any]:
        """Send the complete plan list and mirror it into the coordinator."""
        pin = resolve_pin(entry, call.data)
        permissions = (
            coordinator.permissions
            if getattr(coordinator, "_permissions_loaded", False)
            else None
        )
        try:
            response = await coordinator.api.send_travel_appointment(
                vin, pin, plans, permissions
            )
        except CheryEuropeException as exc:
            raise HomeAssistantError(
                f"Chery Europe preparation command failed: {exc}"
            ) from exc
        if not response.get("ok"):
            message = response.get("message") or response.get("code")
            raise CheryEuropeCommandError(
                f"Chery Europe preparation command failed: {message}"
            )
        coordinator.invalidate_prepare_cache()
        if coordinator.data is not None:
            coordinator.async_set_updated_data(
                apply_travel_appointment(
                    coordinator.data,
                    plans,
                    polled_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        coordinator.schedule_refresh_after_command()
        return response

    async def handle_get_messages(call: ServiceCall) -> dict[str, Any]:
        entry = _get_loaded_entry(hass)
        coordinator = _coordinator_for_call(entry, call.data.get(ATTR_VIN))
        return await coordinator.async_messages_page(
            call.data[ATTR_PAGE],
            call.data[ATTR_PAGE_SIZE],
            unread_only=call.data[ATTR_UNREAD_ONLY],
        )

    def _prepare_body(plans: list[dict[str, Any]]) -> dict[str, Any]:
        """Build the payload without sending it (dry-run helper)."""
        from .vehicle_commands import build_travel_appoint_body

        return build_travel_appoint_body({"plans": plans})

    if not hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_COMMAND,
            handle_send_command,
            schema=SEND_COMMAND_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULED_CHARGING):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_SCHEDULED_CHARGING,
            handle_set_scheduled_charging,
            schema=SET_SCHEDULED_CHARGING_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SET_PREPARE_PLAN):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SET_PREPARE_PLAN,
            handle_set_prepare_plan,
            schema=SET_PREPARE_PLAN_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_CANCEL_PREPARE_PLAN):
        hass.services.async_register(
            DOMAIN,
            SERVICE_CANCEL_PREPARE_PLAN,
            handle_cancel_prepare_plan,
            schema=CANCEL_PREPARE_PLAN_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_GET_MESSAGES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_GET_MESSAGES,
            handle_get_messages,
            schema=GET_MESSAGES_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_LIST_PREPARE_PLANS):
        hass.services.async_register(
            DOMAIN,
            SERVICE_LIST_PREPARE_PLANS,
            handle_list_prepare_plans,
            schema=LIST_PREPARE_PLANS_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )


def _coordinator_for_call(
    entry: ConfigEntry, vin: str | None
) -> CheryEuropeDataUpdateCoordinator:
    """Pick the vehicle coordinator. ``vin`` is required when several are loaded."""
    from .entity import iter_entry_coordinators

    coordinators = iter_entry_coordinators(entry)
    if vin:
        for coordinator in coordinators:
            data = getattr(coordinator, "data", None)
            if getattr(data, "vin", None) == vin or getattr(coordinator, "vin_filter", None) == vin:
                return coordinator
        raise HomeAssistantError("Vehicle is unavailable")
    if len(coordinators) == 1:
        return coordinators[0]
    raise HomeAssistantError("More than one vehicle is configured; pass vin")


def _get_loaded_entry(hass: HomeAssistant) -> ConfigEntry:
    """Return the loaded Chery Europe config entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    loaded = [entry for entry in entries if entry.runtime_data is not None]
    if not loaded:
        raise HomeAssistantError("No loaded Chery Europe config entry found")
    return loaded[0]
