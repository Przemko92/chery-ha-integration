"""Local configuration number entities for Chery Europe."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CheryEuropeDataUpdateCoordinator
from .entity import CheryEuropeEntity

PARALLEL_UPDATES = 0

CHARGE_DURATION_DESCRIPTION = NumberEntityDescription(
    key="charge_duration_hours",
    name="Scheduled charging duration",
    translation_key="charge_duration_hours",
    icon="mdi:battery-clock",
    entity_category=EntityCategory.CONFIG,
    native_min_value=1,
    native_max_value=12,
    native_step=1,
    native_unit_of_measurement=UnitOfTime.HOURS,
    mode=NumberMode.BOX,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe number entities from a config entry."""
    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    async_add_entities([CheryEuropeChargeDurationNumber(coordinator, entry)])


class CheryEuropeChargeDurationNumber(CheryEuropeEntity, RestoreNumber):
    """Scheduled charging duration in hours, used when enabling the plan."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the charge duration entity."""
        super().__init__(coordinator, CHARGE_DURATION_DESCRIPTION, entry)
        self._value = 6.0
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{CHARGE_DURATION_DESCRIPTION.key}"
        coordinator.charge_duration_hours = int(self._value)

    async def async_added_to_hass(self) -> None:
        """Restore the last configured charge duration."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._value = float(last.native_value)
        self._sync_coordinator()

    def _sync_coordinator(self) -> None:
        self.coordinator.charge_duration_hours = int(self._value)

    @property
    def native_value(self) -> float:
        """Return the configured charge duration."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Persist a new scheduled charging duration."""
        self._value = float(value)
        self._sync_coordinator()
        self.async_write_ha_state()
