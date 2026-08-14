"""Services for the Chery Europe integration."""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import ATTR_COMMAND_ID, ATTR_PIN, ATTR_VIN, DOMAIN, SERVICE_SEND_COMMAND
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import apply_command_feedback
from .exceptions import CheryEuropeCommandError, CheryEuropeException

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_VIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Required(ATTR_COMMAND_ID): vol.All(cv.string, vol.Length(min=1)),
        vol.Required(ATTR_PIN): vol.All(cv.string, vol.Length(min=1)),
        vol.Optional("temperature"): vol.Coerce(float),
        vol.Optional("enabled"): cv.boolean,
        vol.Optional("hvac_mode"): cv.string,
        vol.Optional("action"): cv.string,
    }
)

_LOGGER = logging.getLogger(__name__)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register Chery Europe services."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return

    async def handle_send_command(call: ServiceCall) -> dict[str, Any]:
        coordinator = _get_loaded_coordinator(hass)
        try:
            response = await coordinator.api.send_command(
                call.data[ATTR_VIN],
                call.data[ATTR_COMMAND_ID],
                call.data[ATTR_PIN],
                action=call.data.get("action"),
                temperature=call.data.get("temperature"),
                enabled=call.data.get("enabled"),
                hvac_mode=call.data.get("hvac_mode"),
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
                        enabled=call.data.get("enabled"),
                    )
                )

            coordinator.schedule_refresh_after_command()
        except HomeAssistantError:
            raise
        except CheryEuropeException:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Unexpected Chery Europe command failure")
            raise HomeAssistantError("Failed to send Chery Europe command") from err
        return {"success": True}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        handle_send_command,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _get_loaded_coordinator(hass: HomeAssistant) -> CheryEuropeDataUpdateCoordinator:
    """Return the loaded Chery Europe coordinator."""
    entries = hass.config_entries.async_entries(DOMAIN)
    loaded = [entry for entry in entries if entry.runtime_data is not None]
    if not loaded:
        raise HomeAssistantError("No loaded Chery Europe config entry found")
    return loaded[0].runtime_data
