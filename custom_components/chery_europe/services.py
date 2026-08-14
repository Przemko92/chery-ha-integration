"""Services for the Chery Europe integration."""

from __future__ import annotations

import logging
from datetime import time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .command_exec import async_send_vehicle_command
from .const import (
    ATTR_COMMAND_ID,
    ATTR_DURATION_HOURS,
    ATTR_ENABLED,
    ATTR_PIN,
    ATTR_START_TIME,
    ATTR_VIN,
    DOMAIN,
    SERVICE_SEND_COMMAND,
    SERVICE_SET_SCHEDULED_CHARGING,
)
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import apply_command_feedback
from .exceptions import CheryEuropeCommandError, CheryEuropeException

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_VIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Required(ATTR_COMMAND_ID): vol.All(cv.string, vol.Length(min=1)),
        vol.Required(ATTR_PIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("temperature"): vol.Coerce(float),
        vol.Optional(ATTR_ENABLED): cv.boolean,
        vol.Optional("hvac_mode"): cv.string,
        vol.Optional("action"): cv.string,
        vol.Optional("seat_field"): cv.string,
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
        vol.Optional(ATTR_VIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional(ATTR_PIN): vol.All(cv.string, vol.Length(min=1)),
    }
)

_LOGGER = logging.getLogger(__name__)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register Chery Europe services."""

    async def handle_send_command(call: ServiceCall) -> dict[str, Any]:
        entry = _get_loaded_entry(hass)
        coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
        try:
            response = await coordinator.api.send_command(
                call.data[ATTR_VIN],
                call.data[ATTR_COMMAND_ID],
                call.data[ATTR_PIN],
                action=call.data.get("action"),
                temperature=call.data.get("temperature"),
                enabled=call.data.get(ATTR_ENABLED),
                hvac_mode=call.data.get("hvac_mode"),
                seat_field=call.data.get("seat_field"),
                start_minutes=call.data.get("start_minutes"),
                duration_hours=call.data.get(ATTR_DURATION_HOURS),
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
        coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
        start: time = call.data[ATTR_START_TIME]
        duration_hours: int = call.data[ATTR_DURATION_HOURS]
        enabled: bool = call.data[ATTR_ENABLED]
        start_minutes = start.hour * 60 + start.minute

        vin = call.data.get(ATTR_VIN) or (
            coordinator.data.vin if coordinator.data is not None else None
        )
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


def _get_loaded_entry(hass: HomeAssistant) -> ConfigEntry:
    """Return the loaded Chery Europe config entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    loaded = [entry for entry in entries if entry.runtime_data is not None]
    if not loaded:
        raise HomeAssistantError("No loaded Chery Europe config entry found")
    return loaded[0]
