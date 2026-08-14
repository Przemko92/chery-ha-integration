"""Local configuration time entities for Chery Europe."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import CheryEuropeDataUpdateCoordinator
from .entity import CheryEuropeEntity

PARALLEL_UPDATES = 0

CHARGE_START_TIME_DESCRIPTION = TimeEntityDescription(
    key="charge_start_time",
    name="Scheduled charging start time",
    translation_key="charge_start_time",
    icon="mdi:clock-start",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe time entities from a config entry."""
    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    async_add_entities([CheryEuropeChargeStartTime(coordinator, entry)])


class CheryEuropeChargeStartTime(CheryEuropeEntity, TimeEntity, RestoreEntity):
    """Scheduled charging start time stored locally and used when enabling the plan."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the charge start time entity."""
        super().__init__(coordinator, CHARGE_START_TIME_DESCRIPTION, entry)
        self._value = time(hour=8, minute=0)
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{CHARGE_START_TIME_DESCRIPTION.key}"
        coordinator.charge_start_minutes = self._value.hour * 60 + self._value.minute

    async def async_added_to_hass(self) -> None:
        """Restore the last configured start time."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, "", "unknown", "unavailable"):
            try:
                hour, minute, *_ = (int(part) for part in last.state.split(":"))
                self._value = time(hour=hour, minute=minute)
            except (ValueError, TypeError):
                pass
        self._sync_coordinator()

    def _sync_coordinator(self) -> None:
        self.coordinator.charge_start_minutes = (
            self._value.hour * 60 + self._value.minute
        )

    @property
    def native_value(self) -> time:
        """Return the configured start time."""
        return self._value

    async def async_set_value(self, value: time) -> None:
        """Persist a new scheduled charging start time."""
        self._value = value.replace(second=0, microsecond=0)
        self._sync_coordinator()
        self.async_write_ha_state()
