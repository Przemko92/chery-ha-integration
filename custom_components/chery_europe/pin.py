"""Resolve the vehicle control PIN for remote commands."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError

from .const import ATTR_PIN, CONF_ASK_FOR_PIN, CONF_PIN


def ask_for_pin(entry: ConfigEntry | None) -> bool:
    """Return whether the user wants to enter the PIN on each action."""
    if entry is None:
        return False
    return bool(entry.options.get(CONF_ASK_FOR_PIN, False))


def _provided_pin(values: dict[str, Any]) -> str | None:
    for key in (ATTR_PIN, "code"):
        value = values.get(key)
        if value:
            return str(value)
    return None


def _stored_pin(entry: ConfigEntry | None) -> str | None:
    if entry is None:
        return None
    stored = entry.options.get(CONF_PIN)
    if stored:
        return str(stored)
    return None


def resolve_pin(entry: ConfigEntry | None, values: dict[str, Any] | None = None) -> str:
    """Return PIN from the service call or integration options.

    When ``ask_for_pin`` is enabled, a PIN/code must be provided and must match
    the stored options PIN before the command is sent.
    """
    values = values or {}
    provided = _provided_pin(values)
    stored = _stored_pin(entry)

    if ask_for_pin(entry):
        if not provided:
            raise HomeAssistantError(
                "Vehicle control PIN is required for this action. "
                "Enter the PIN, or disable Ask for PIN in Chery Europe options."
            )
        if not stored:
            raise HomeAssistantError(
                "Vehicle control PIN is not configured. "
                "Open Chery Europe integration settings and set the PIN."
            )
        if provided != stored:
            raise HomeAssistantError(
                "Entered PIN does not match the stored vehicle control PIN."
            )
        return stored

    if provided:
        return provided
    if stored:
        return stored
    raise HomeAssistantError(
        "Vehicle control PIN is not configured. "
        "Open Chery Europe integration settings and set the PIN."
    )
