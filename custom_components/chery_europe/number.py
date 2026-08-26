"""Local configuration number entities for Chery Europe."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberEntityDescription,
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .charge_schedule import plan_duration_hours
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
    """Scheduled charging duration; mirrors the vehicle plan when available."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the charge duration entity."""
        super().__init__(coordinator, CHARGE_DURATION_DESCRIPTION, entry)
        self._value = 6.0
        self._user_set = False
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{CHARGE_DURATION_DESCRIPTION.key}"
        self._apply_vehicle_plan()
        self._sync_coordinator()

    async def async_added_to_hass(self) -> None:
        """Restore last HA value, then prefer the live vehicle plan."""
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self._value = float(last.native_value)
        # Vehicle plan wins over a stale restored draft so HA matches the car.
        self._apply_vehicle_plan()
        self._sync_coordinator()

    def _apply_vehicle_plan(self) -> bool:
        """Copy duration from the vehicle plan. Return True if applied."""
        hours = plan_duration_hours(self.chery_data.charge_appoint_plan)
        if hours is None:
            return False
        max_hours = int(CHARGE_DURATION_DESCRIPTION.native_max_value or 12)
        self._value = float(min(hours, max_hours))
        self._user_set = False
        return True

    def _sync_coordinator(self) -> None:
        self.coordinator.charge_duration_hours = int(self._value)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Keep the entity aligned with the vehicle unless the user edited it."""
        plan_hours = plan_duration_hours(self.chery_data.charge_appoint_plan)
        if self._user_set:
            if plan_hours is not None and float(plan_hours) == self._value:
                self._user_set = False
        elif plan_hours is not None and float(plan_hours) != self._value:
            max_hours = int(CHARGE_DURATION_DESCRIPTION.native_max_value or 12)
            self._value = float(min(plan_hours, max_hours))
            self._sync_coordinator()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        """Return the configured charge duration."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Persist a new scheduled charging duration."""
        self._value = float(value)
        self._user_set = True
        self._sync_coordinator()
        self.async_write_ha_state()
