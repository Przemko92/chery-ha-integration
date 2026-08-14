"""Shared helper to send PIN-protected vehicle commands from entities."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import apply_command_feedback
from .exceptions import CheryEuropeCommandError, CheryEuropeException
from .pin import resolve_pin


async def async_send_vehicle_command(
    coordinator: CheryEuropeDataUpdateCoordinator,
    entry: ConfigEntry,
    vin: str | None,
    kwargs: dict[str, Any],
    *,
    command_id: str,
    **command_kwargs: Any,
) -> None:
    """Send a remote command and apply optimistic coordinator feedback."""
    pin = resolve_pin(entry, kwargs)
    if not vin:
        raise HomeAssistantError("Vehicle VIN is unavailable")
    try:
        response = await coordinator.api.send_command(
            vin,
            command_id,
            pin,
            **command_kwargs,
        )
        if not response.get("ok"):
            message = response.get("message") or response.get("code")
            raise CheryEuropeCommandError(f"Chery Europe command failed: {message}")
        if coordinator.data is not None:
            coordinator.async_set_updated_data(
                apply_command_feedback(
                    coordinator.data,
                    command_id,
                    **command_kwargs,
                )
            )
        coordinator.schedule_refresh_after_command()
        if command_id == "ve_1209":
            coordinator.schedule_location_refresh()
    except CheryEuropeException:
        raise
    except Exception as err:  # noqa: BLE001
        raise HomeAssistantError("Failed to send Chery Europe command") from err
