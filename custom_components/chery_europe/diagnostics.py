from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, VERSION

TO_REDACT = {
    "access_token",
    "refresh_token",
    "password",
    "code",
    "pin",
    "vin",
    "latitude",
    "longitude",
    "account_id",
    "client_secret",
    "clientsecret",
    "login",
}
REDACTED = "***REDACTED***"


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry with sensitive data redacted."""
    registry = er.async_get(hass)
    entity_entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    coordinator = getattr(entry, "runtime_data", None)

    return _redact(
        {
            "integration_version": VERSION,
            "ha_version": HA_VERSION,
            "entry_id": entry.entry_id,
            "domain": DOMAIN,
            "config_entry_data": dict(entry.data),
            "entity_count": len(entity_entries),
            "entity_ids": [entity.entity_id for entity in entity_entries],
            "last_update_success": getattr(coordinator, "last_update_success", None),
            "last_update": str(getattr(coordinator, "last_update_success_time", None)),
            "data": getattr(coordinator, "data", None),
        }
    )


def _redact(value: Any) -> Any:
    """Recursively redact sensitive diagnostic values."""
    if isinstance(value, dict):
        return {
            key: REDACTED if str(key).lower() in TO_REDACT else _redact(item)
            for key, item in value.items()
        }
    if hasattr(value, "__dataclass_fields__"):
        return _redact(value.__dict__)
    if isinstance(value, list | tuple):
        return [_redact(item) for item in value]
    return value
