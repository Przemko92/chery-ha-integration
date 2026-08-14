"""Local configuration number entities for Chery Europe."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CheryEuropeDataUpdateCoordinator
from .entity import CheryEuropeEntity

PARALLEL_UPDATES = 0


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

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:battery-clock"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_max_value = 12
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_translation_key = "charge_duration_hours"

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the charge duration entity."""
        super().__init__(coordinator, None, entry)
        self._value = 6.0
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_charge_duration_hours"
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
