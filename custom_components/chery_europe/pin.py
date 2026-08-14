"""Resolve the vehicle control PIN for remote commands."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

from .const import ATTR_PIN, CONF_PIN


def resolve_pin(entry: ConfigEntry | None, values: dict[str, Any] | None = None) -> str:
    """Return PIN from the service call or integration options."""
    values = values or {}
    for key in (ATTR_PIN, "code"):
        value = values.get(key)
        if value:
            return str(value)
    if entry is not None:
        stored = entry.options.get(CONF_PIN)
        if stored:
            return str(stored)
    raise HomeAssistantError(
        "Vehicle control PIN is not configured. "
        "Open Chery Europe integration settings and set the PIN."
    )
