"""Local configuration time entities for Chery Europe."""

from __future__ import annotations

from datetime import time
from typing import Any

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .charge_schedule import (
    CHARGE_DURATION_MAX_MINUTES,
    duration_for_end,
    format_minutes_as_hhmm,
    local_time_to_minutes,
    minutes_to_local_time,
    plan_duration_minutes,
    plan_start_time,
    snap_duration_minutes,
    window_minutes,
)
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
)

CHARGE_END_TIME_DESCRIPTION = TimeEntityDescription(
    key="charge_end_time",
    name="Scheduled charging end time",
    translation_key="charge_end_time",
    icon="mdi:clock-end",
)

DEPARTURE_TIME_DESCRIPTION = TimeEntityDescription(
    key="departure_time",
    name="Departure time",
    translation_key="departure_time",
    icon="mdi:clock-out",
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
        if keep_feature(perms, CHARGE_END_TIME_DESCRIPTION.key, f"{vin}_charge_end_time", removed):
            entities.append(CheryEuropeChargeEndTime(coordinator, entry))
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
        self.coordinator.charge_schedule_listeners.append(self)
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

    async def async_will_remove_from_hass(self) -> None:
        """Stop listening once the entity is gone."""
        listeners = getattr(self.coordinator, "charge_schedule_listeners", None)
        if listeners and self in listeners:
            listeners.remove(self)
        await super().async_will_remove_from_hass()

    def _sync_coordinator(self, duration_hours: float | None = None) -> None:
        self.coordinator.charge_start_minutes = local_time_to_minutes(self._value)
        if duration_hours is not None:
            self.coordinator.charge_duration_hours = duration_hours

    def _duration_keeping_end(self, new_start: int) -> float:
        """Return the duration that leaves the current end where it is."""
        start = int(self.coordinator.charge_start_minutes)
        minutes = snap_duration_minutes(round(float(self.coordinator.charge_duration_hours) * 60))
        if minutes >= CHARGE_DURATION_MAX_MINUTES:
            # A full day has no distinct end; moving the start keeps it full.
            return minutes / 60
        end, _ = window_minutes(start, minutes)
        return duration_for_end(new_start, end) / 60

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
        """Move the start and keep the end, so the window shortens or grows."""
        new_value = value.replace(second=0, microsecond=0)
        new_start = local_time_to_minutes(new_value)
        hours = self._duration_keeping_end(new_start)
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            {},
            command_id="ve_1202",
            enabled=bool(self.chery_data.scheduled_charge_enabled),
            start_minutes=new_start,
            duration_hours=hours,
        )
        self._value = new_value
        self._sync_coordinator(hours)
        self.coordinator.async_notify_charge_schedule()
        self.async_write_ha_state()


class CheryEuropeChargeEndTime(CheryEuropeEntity, TimeEntity):
    """Charging end time, derived from the start time and the duration.

    The car stores a start and a duration, so the end is never written to it
    directly: changing the end rewrites the duration, and changing either the
    start or the duration moves the end accordingly. A window that runs past
    midnight ends on the next day; the attributes say so.
    """

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the charge end time entity."""
        super().__init__(coordinator, CHARGE_END_TIME_DESCRIPTION, entry)
        self._attr_unique_id = stable_unique_id(
            entry, CHARGE_END_TIME_DESCRIPTION.key, coordinator
        )

    async def async_added_to_hass(self) -> None:
        """Join the schedule group so the other two entities refresh the end."""
        await super().async_added_to_hass()
        self.coordinator.charge_schedule_listeners.append(self)

    async def async_will_remove_from_hass(self) -> None:
        """Stop listening once the entity is gone."""
        listeners = getattr(self.coordinator, "charge_schedule_listeners", None)
        if listeners and self in listeners:
            listeners.remove(self)
        await super().async_will_remove_from_hass()

    def _duration_minutes(self) -> int:
        """Return the duration the coordinator holds, on the car's grid."""
        return snap_duration_minutes(round(float(self.coordinator.charge_duration_hours) * 60))

    @callback
    def _handle_coordinator_update(self) -> None:
        """Take the duration from the plan before rendering the end."""
        minutes = plan_duration_minutes(self.chery_data.charge_appoint_plan)
        if minutes is not None:
            self.coordinator.charge_duration_hours = minutes / 60
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> time:
        """Return the start plus the duration, wrapped into the next day."""
        end, _ = window_minutes(int(self.coordinator.charge_start_minutes), self._duration_minutes())
        return minutes_to_local_time(end)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the window the end time was derived from."""
        start = int(self.coordinator.charge_start_minutes)
        minutes = self._duration_minutes()
        end, next_day = window_minutes(start, minutes)
        return {
            "start_time": format_minutes_as_hhmm(start),
            "end_time": format_minutes_as_hhmm(end),
            "duration_hours": minutes / 60,
            "next_day": next_day,
        }

    async def async_set_value(self, value: time) -> None:
        """Move the end and shorten or lengthen the duration to match it."""
        start = int(self.coordinator.charge_start_minutes)
        hours = duration_for_end(start, local_time_to_minutes(value.replace(second=0, microsecond=0))) / 60
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            {},
            command_id="ve_1202",
            enabled=bool(self.chery_data.scheduled_charge_enabled),
            start_minutes=start,
            duration_hours=hours,
        )
        self.coordinator.charge_duration_hours = hours
        self.coordinator.async_notify_charge_schedule()
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
