from typing import Any

import voluptuous as vol
from homeassistant.components.lock import LockEntity, LockEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform

from .const import (
    ATTR_COMMAND_ID,
    ATTR_PIN,
    DOMAIN,
    LOCK,
    SERVICE_SEND_COMMAND,
)
from .coordinator import CheryEuropeDataUpdateCoordinator
from .entity import (
    CheryEuropeEntity,
    async_remove_unsupported,
    control_permissions,
    keep_feature,
    stable_unique_id,
    vehicle_uid,
)
from .pin import ask_for_pin, resolve_pin

PARALLEL_UPDATES = 0

LOCK_COMMAND_ID = "ve_1105"
PIN_SCHEMA = cv.make_entity_service_schema(
    {vol.Optional(ATTR_PIN): vol.All(cv.string, vol.Length(min=1))}
)

LOCK_DESCRIPTION = LockEntityDescription(
    key="doors",
    name="Doors",
    translation_key="doors",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Chery Europe lock from a config entry."""
    platform = async_get_current_platform()
    platform.async_register_entity_service(
        "lock",
        PIN_SCHEMA,
        "async_lock",
        supports_response=SupportsResponse.NONE,
    )
    platform.async_register_entity_service(
        "unlock",
        PIN_SCHEMA,
        "async_unlock",
        supports_response=SupportsResponse.NONE,
    )

    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    perms = control_permissions(coordinator)
    vin = vehicle_uid(coordinator, entry)
    removed: list[str] = []
    if keep_feature(perms, LOCK_DESCRIPTION.key, f"{vin}_doors_lock", removed):
        async_add_entities([CheryEuropeLock(coordinator, LOCK_DESCRIPTION, entry)])
    async_remove_unsupported(hass, LOCK, removed)


class CheryEuropeLock(CheryEuropeEntity, LockEntity):
    """Representation of Chery Europe vehicle door locks."""

    entity_description: LockEntityDescription
    _attr_assumed_state = False

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: LockEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the lock."""
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        self._attr_unique_id = stable_unique_id(entry, f"{description.key}_lock")

    @property
    def code_format(self) -> str | None:
        """Require a code when Ask for PIN is enabled."""
        if ask_for_pin(self._entry):
            return r".+"
        return None

    @property
    def is_locked(self) -> bool | None:  # type: ignore[reportIncompatibleVariableOverride]
        """Return the current lock state from coordinator data."""
        return self.chery_data.is_locked

    @property
    def assumed_state(self) -> bool:  # type: ignore[reportIncompatibleVariableOverride]
        """Return false because the API reports real lock state."""
        return False

    @property
    def available(self) -> bool:  # type: ignore[reportIncompatibleVariableOverride]
        """Return if lock data is available."""
        return self.chery_data.is_locked is not None and super().available

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the vehicle doors using the PIN from the service call."""
        await self._send_lock_command("lock", kwargs)

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the vehicle doors using the PIN from the service call."""
        await self._send_lock_command("unlock", kwargs)

    async def _send_lock_command(self, action: str, kwargs: dict[str, Any]) -> None:
        """Call the Chery Europe command service with the resolved PIN."""
        pin = resolve_pin(self._entry, kwargs)
        if not self.chery_data.vin:
            raise HomeAssistantError("Vehicle is unavailable")

        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_COMMAND,
            {
                ATTR_COMMAND_ID: LOCK_COMMAND_ID,
                ATTR_PIN: pin,
                "action": action,
            },
            blocking=True,
        )
