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

from .charge_schedule import plan_duration_hours, snap_duration_minutes
from .command_exec import async_send_vehicle_command
from .const import NUMBER
from .coordinator import CheryEuropeDataUpdateCoordinator
from .entity import (
    CheryEuropeEntity,
    async_remove_unsupported,
    control_permissions,
    iter_entry_coordinators,
    keep_feature,
    stable_unique_id,
    vehicle_uid,
)

PARALLEL_UPDATES = 0

CHARGE_DURATION_DESCRIPTION = NumberEntityDescription(
    key="charge_duration_hours",
    name="Scheduled charging duration",
    translation_key="charge_duration_hours",
    icon="mdi:battery-clock",
    entity_category=EntityCategory.CONFIG,
    native_min_value=0.25,
    native_max_value=24,
    native_step=0.25,
    native_unit_of_measurement=UnitOfTime.HOURS,
    mode=NumberMode.BOX,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe number entities from a config entry."""
    removed: list[str] = []
    entities = []
    for coordinator in iter_entry_coordinators(entry):
        perms = control_permissions(coordinator)
        vin = vehicle_uid(coordinator, entry)
        if keep_feature(
            perms,
            CHARGE_DURATION_DESCRIPTION.key,
            f"{vin}_charge_duration_hours",
            removed,
        ):
            entities.append(CheryEuropeChargeDurationNumber(coordinator, entry))
    async_add_entities(entities)
    async_remove_unsupported(hass, NUMBER, removed)


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
        self._attr_unique_id = stable_unique_id(entry, CHARGE_DURATION_DESCRIPTION.key, coordinator)
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
        self._value = self._snap(hours)
        return True

    def _sync_coordinator(self) -> None:
        self.coordinator.charge_duration_hours = self._value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Keep the entity aligned with the plan reported by the vehicle."""
        plan_hours = plan_duration_hours(self.chery_data.charge_appoint_plan)
        if plan_hours is not None and self._snap(plan_hours) != self._value:
            self._value = self._snap(plan_hours)
            self._sync_coordinator()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> float:
        """Return the configured charge duration."""
        return self._value

    @staticmethod
    def _snap(value: float) -> float:
        """Snap an hour value to the 15 minute grid the car accepts."""
        return snap_duration_minutes(float(value) * 60) / 60

    async def async_set_native_value(self, value: float) -> None:
        """Send a new scheduled charging duration to the vehicle."""
        hours = self._snap(value)
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            {},
            command_id="ve_1202",
            enabled=bool(self.chery_data.scheduled_charge_enabled),
            start_minutes=int(self.coordinator.charge_start_minutes),
            duration_hours=hours,
        )
        self._value = hours
        self._sync_coordinator()
        self.async_write_ha_state()
