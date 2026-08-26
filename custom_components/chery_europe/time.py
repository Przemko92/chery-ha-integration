"""Local configuration time entities for Chery Europe."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .charge_schedule import local_time_to_minutes, plan_start_time
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
    """Scheduled charging start time; mirrors the vehicle plan when available."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the charge start time entity."""
        super().__init__(coordinator, CHARGE_START_TIME_DESCRIPTION, entry)
        self._value = time(hour=8, minute=0)
        self._user_set = False
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{CHARGE_START_TIME_DESCRIPTION.key}"
        self._apply_vehicle_plan()
        self._sync_coordinator()

    async def async_added_to_hass(self) -> None:
        """Restore last HA value, then prefer the live vehicle plan."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, "", "unknown", "unavailable"):
            try:
                hour, minute, *_ = (int(part) for part in last.state.split(":"))
                self._value = time(hour=hour, minute=minute)
            except (ValueError, TypeError):
                pass
        # Vehicle plan wins over a stale restored draft so HA matches the car.
        self._apply_vehicle_plan()
        self._sync_coordinator()

    def _apply_vehicle_plan(self) -> bool:
        """Copy start time from the vehicle plan. Return True if applied."""
        start = plan_start_time(self.chery_data.charge_appoint_plan)
        if start is None:
            return False
        self._value = start
        self._user_set = False
        return True

    def _sync_coordinator(self) -> None:
        self.coordinator.charge_start_minutes = local_time_to_minutes(self._value)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Keep the entity aligned with the vehicle unless the user edited it."""
        plan_start = plan_start_time(self.chery_data.charge_appoint_plan)
        if self._user_set:
            if plan_start is not None and plan_start == self._value:
                self._user_set = False
        elif plan_start is not None and plan_start != self._value:
            self._value = plan_start
            self._sync_coordinator()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> time:
        """Return the configured start time in the Home Assistant local zone."""
        return self._value

    async def async_set_value(self, value: time) -> None:
        """Persist a new scheduled charging start time (local wall clock)."""
        self._value = value.replace(second=0, microsecond=0)
        self._user_set = True
        self._sync_coordinator()
        self.async_write_ha_state()
