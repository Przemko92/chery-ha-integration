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
from .command_exec import async_send_vehicle_command
from .const import TIME
from .coordinator import CheryEuropeDataUpdateCoordinator
from .departure import async_set_departure, departure_state
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

CHARGE_START_TIME_DESCRIPTION = TimeEntityDescription(
    key="charge_start_time",
    name="Scheduled charging start time",
    translation_key="charge_start_time",
    icon="mdi:clock-start",
    entity_category=EntityCategory.CONFIG,
)

DEPARTURE_TIME_DESCRIPTION = TimeEntityDescription(
    key="departure_time",
    name="Departure time",
    translation_key="departure_time",
    icon="mdi:clock-out",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe time entities from a config entry."""
    removed: list[str] = []
    entities = []
    for coordinator in iter_entry_coordinators(entry):
        perms = control_permissions(coordinator)
        vin = vehicle_uid(coordinator, entry)
        if keep_feature(perms, CHARGE_START_TIME_DESCRIPTION.key, f"{vin}_charge_start_time", removed):
            entities.append(CheryEuropeChargeStartTime(coordinator, entry))
        if keep_feature(perms, DEPARTURE_TIME_DESCRIPTION.key, f"{vin}_departure_time", removed):
            entities.append(CheryEuropeDepartureTime(coordinator, entry))
    async_add_entities(entities)
    async_remove_unsupported(hass, TIME, removed)


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
        self._attr_unique_id = stable_unique_id(entry, CHARGE_START_TIME_DESCRIPTION.key, coordinator)
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
        return True

    def _sync_coordinator(self) -> None:
        self.coordinator.charge_start_minutes = local_time_to_minutes(self._value)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Keep the entity aligned with the plan reported by the vehicle."""
        plan_start = plan_start_time(self.chery_data.charge_appoint_plan)
        if plan_start is not None and plan_start != self._value:
            self._value = plan_start
            self._sync_coordinator()
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> time:
        """Return the configured start time in the Home Assistant local zone."""
        return self._value

    async def async_set_value(self, value: time) -> None:
        """Send a new scheduled charging start time to the vehicle."""
        new_value = value.replace(second=0, microsecond=0)
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            {},
            command_id="ve_1202",
            enabled=bool(self.chery_data.scheduled_charge_enabled),
            start_minutes=local_time_to_minutes(new_value),
            duration_hours=int(self.coordinator.charge_duration_hours),
        )
        self._value = new_value
        self._sync_coordinator()
        self.async_write_ha_state()


class CheryEuropeDepartureTime(CheryEuropeEntity, TimeEntity, RestoreEntity):
    """Departure time of the preparation plan the departure switch arms."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the departure time entity."""
        super().__init__(coordinator, DEPARTURE_TIME_DESCRIPTION, entry)
        self._attr_unique_id = stable_unique_id(
            entry, DEPARTURE_TIME_DESCRIPTION.key, coordinator
        )
        self._value = _as_time(departure_state(coordinator)[0])

    async def async_added_to_hass(self) -> None:
        """Restore the last commanded time; the car cannot be read back."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, "", "unknown", "unavailable"):
            try:
                hour, minute, *_ = (int(part) for part in last.state.split(":"))
            except (TypeError, ValueError):
                pass
            else:
                if self.coordinator.departure_draft is None:
                    self.coordinator.departure_draft = f"{hour:02d}:{minute:02d}"
        self._value = _as_time(departure_state(self.coordinator)[0])


    @callback
    def _handle_coordinator_update(self) -> None:
        """Follow the plan the vehicle reports."""
        travel_time, _armed = departure_state(self.coordinator)
        self._value = _as_time(travel_time)
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> time:
        """Return the configured departure time."""
        return self._value

    async def async_set_value(self, value: time) -> None:
        """Store the departure time, updating the vehicle plan when it exists."""
        new_value = value.replace(second=0, microsecond=0)
        await async_set_departure(
            self.coordinator,
            self._entry,
            travel_time=f"{new_value.hour:02d}:{new_value.minute:02d}",
        )
        self._value = new_value
        self.async_write_ha_state()


def _as_time(value: str) -> time:
    """Convert ``HH:MM`` into a :class:`datetime.time`."""
    hour, minute, *_ = (int(part) for part in value.split(":"))
    return time(hour=hour, minute=minute)
