"""Switch platform for safe Chery Europe remote commands."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .charge_schedule import plan_duration_hours, plan_start_time
from .command_exec import async_send_vehicle_command
from .const import SWITCH
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import CheryData, climate_at_hi, climate_at_lo
from .departure import (
    async_set_departure,
    async_set_departure_days,
    departure_days,
    departure_state,
)
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

DEPARTURE_SWITCH_DESCRIPTION = SwitchEntityDescription(
    key="departure",
    name="Departure plan",
    translation_key="departure",
    icon="mdi:car-clock",
    entity_category=EntityCategory.CONFIG,
)

#: One switch per weekday, so the departure plan can be limited per day.
DEPARTURE_DAY_DESCRIPTIONS: tuple[tuple[int, SwitchEntityDescription], ...] = (
    (
        1,
        SwitchEntityDescription(
            key="departure_monday",
            name="Departure plan Monday",
            translation_key="departure_monday",
            icon="mdi:calendar-today",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    (
        2,
        SwitchEntityDescription(
            key="departure_tuesday",
            name="Departure plan Tuesday",
            translation_key="departure_tuesday",
            icon="mdi:calendar-today",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    (
        3,
        SwitchEntityDescription(
            key="departure_wednesday",
            name="Departure plan Wednesday",
            translation_key="departure_wednesday",
            icon="mdi:calendar-today",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    (
        4,
        SwitchEntityDescription(
            key="departure_thursday",
            name="Departure plan Thursday",
            translation_key="departure_thursday",
            icon="mdi:calendar-today",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    (
        5,
        SwitchEntityDescription(
            key="departure_friday",
            name="Departure plan Friday",
            translation_key="departure_friday",
            icon="mdi:calendar-today",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    (
        6,
        SwitchEntityDescription(
            key="departure_saturday",
            name="Departure plan Saturday",
            translation_key="departure_saturday",
            icon="mdi:calendar-weekend",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    (
        7,
        SwitchEntityDescription(
            key="departure_sunday",
            name="Departure plan Sunday",
            translation_key="departure_sunday",
            icon="mdi:calendar-weekend",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
)



@dataclass(frozen=True, kw_only=True)
class CheryEuropeSwitchEntityDescription(SwitchEntityDescription):
    """Describes a safe Chery Europe command switch."""

    command_id: str
    state_fn: Callable[[CheryData], bool | None]
    command_values: dict[str, Any] | None = None


SWITCH_DESCRIPTIONS: tuple[CheryEuropeSwitchEntityDescription, ...] = (
    CheryEuropeSwitchEntityDescription(
        key="front_windshield_heating",
        name="Front windshield heating",
        translation_key="front_windshield_heating",
        icon="mdi:car-defrost-front",
        command_id="ve_1103",
        state_fn=lambda data: data.front_windshield_heating,
    ),
    CheryEuropeSwitchEntityDescription(
        key="front_windshield_defrost",
        name="Front windshield defrost",
        translation_key="front_windshield_defrost",
        icon="mdi:car-defrost-front",
        command_id="ve_1108",
        state_fn=lambda data: data.front_windshield_defrost,
    ),
    CheryEuropeSwitchEntityDescription(
        key="air_purification",
        name="Air purification",
        translation_key="air_purification",
        icon="mdi:air-purifier",
        command_id="ve_1109",
        state_fn=lambda data: data.air_purification,
    ),
    CheryEuropeSwitchEntityDescription(
        key="rear_window_defrost",
        name="Rear window heating",
        translation_key="rear_window_defrost",
        icon="mdi:car-defrost-rear",
        command_id="ve_1135",
        state_fn=lambda data: data.rear_window_defrost,
    ),
    CheryEuropeSwitchEntityDescription(
        key="steering_wheel_heating",
        name="Steering wheel heating",
        translation_key="steering_wheel_heating",
        icon="mdi:steering",
        command_id="ve_1203",
        state_fn=lambda data: data.steering_wheel_heating,
    ),
    # Seat heating/ventilation are three-level functions, so they live in the
    # select platform (see select.py, SEAT_SELECT_DESCRIPTIONS) instead of a
    # plain switch that could only send on/off at level 3.
    CheryEuropeSwitchEntityDescription(
        key="heat_everything",
        name="Climate HI",
        translation_key="heat_everything",
        icon="mdi:thermometer-high",
        command_id="ve_1301",
        state_fn=climate_at_hi,
    ),
    CheryEuropeSwitchEntityDescription(
        key="cool_everything",
        name="Climate LO",
        translation_key="cool_everything",
        icon="mdi:thermometer-low",
        command_id="ve_1302",
        state_fn=climate_at_lo,
    ),
    CheryEuropeSwitchEntityDescription(
        key="theft_alarm",
        name="Theft alarm",
        translation_key="theft_alarm",
        icon="mdi:shield-car",
        command_id="ve_1303",
        state_fn=lambda data: data.theft_alarm,
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe switches from a config entry."""
    removed: list[str] = []
    entities: list[SwitchEntity] = []
    for coordinator in iter_entry_coordinators(entry):
        perms = control_permissions(coordinator)
        vin = vehicle_uid(coordinator, entry)
        entities.extend(
            CheryEuropeCommandSwitch(coordinator, description, entry)
            for description in SWITCH_DESCRIPTIONS
            if keep_feature(perms, description.key, f"{vin}_{description.key}", removed)
        )
        if keep_feature(perms, "charging_switch", f"{vin}_charging_switch", removed):
            entities.append(CheryEuropeChargeSwitch(coordinator, entry))
        if keep_feature(perms, "scheduled_charging", f"{vin}_scheduled_charging", removed):
            entities.append(CheryEuropeScheduledChargeSwitch(coordinator, entry))
        if keep_feature(perms, "departure", f"{vin}_departure", removed):
            entities.append(CheryEuropeDepartureSwitch(coordinator, entry))
        entities.extend(
            CheryEuropeDepartureDaySwitch(coordinator, description, entry, day)
            for day, description in DEPARTURE_DAY_DESCRIPTIONS
            if keep_feature(perms, description.key, f"{vin}_{description.key}", removed)
        )
        entities.append(CheryEuropePollingSwitch(coordinator, entry))
    async_remove_unsupported(hass, SWITCH, removed)
    async_add_entities(entities)


class CheryEuropeCommandSwitch(CheryEuropeEntity, SwitchEntity):
    """Representation of a safe Chery Europe command switch."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: CheryEuropeSwitchEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        self._attr_unique_id = stable_unique_id(entry, description.key, coordinator)

    @property
    def is_on(self) -> bool | None:  # type: ignore[reportIncompatibleVariableOverride]
        """Return the switch state from coordinator feedback, if available."""
        description = self.entity_description
        assert isinstance(description, CheryEuropeSwitchEntityDescription)
        return description.state_fn(self.chery_data)

    @property
    def assumed_state(self) -> bool:  # type: ignore[reportIncompatibleVariableOverride]
        """Return true when the API does not provide reliable command feedback."""
        return self.is_on is None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Send the safe remote command using the PIN from the service call."""
        await self._send_command(kwargs, enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Send the safe remote command using the PIN from the service call."""
        await self._send_command(kwargs, enabled=False)

    async def _send_command(self, kwargs: dict[str, Any], *, enabled: bool) -> None:
        """Send this switch command without storing or logging the PIN."""
        extra = dict(self.command_description.command_values or {})
        extra["enabled"] = enabled
        if self.command_description.command_id == "ve_1108":
            # the defrost rides on airControl: keep the current climate target
            extra["temperature"] = self.chery_data.target_temperature
        elif self.command_description.command_id == "ve_1109":
            # purification rides on airControl too; OFF keeps the climate state
            extra["temperature"] = self.chery_data.target_temperature
            extra["hvac_enabled"] = self.chery_data.hvac_enabled
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            kwargs,
            command_id=self.command_description.command_id,
            **extra,
        )

    @property
    def available(self) -> bool:  # type: ignore[reportIncompatibleVariableOverride]
        """Return if entity data is available."""
        return self.coordinator.data is not None and super().available

    @property
    def command_description(self) -> CheryEuropeSwitchEntityDescription:
        """Return the typed switch description."""
        description = self.entity_description
        assert isinstance(description, CheryEuropeSwitchEntityDescription)
        return description


POLLING_SWITCH_DESCRIPTION = SwitchEntityDescription(
    key="automatic_updates",
    name="Automatic updates",
    translation_key="automatic_updates",
    icon="mdi:autorenew",
    entity_category=EntityCategory.CONFIG,
)

CHARGING_SWITCH_DESCRIPTION = SwitchEntityDescription(
    key="charging_switch",
    name="Charging",
    translation_key="charging",
    icon="mdi:battery-charging",
)

SCHEDULED_CHARGING_SWITCH_DESCRIPTION = SwitchEntityDescription(
    key="scheduled_charging",
    name="Scheduled charging",
    translation_key="scheduled_charging",
    icon="mdi:calendar-clock",
    entity_category=EntityCategory.CONFIG,
)


class CheryEuropePollingSwitch(CheryEuropeEntity, SwitchEntity, RestoreEntity):
    """Enable or disable automatic telemetry polling."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, POLLING_SWITCH_DESCRIPTION, entry)
        self._attr_unique_id = stable_unique_id(entry, POLLING_SWITCH_DESCRIPTION.key, coordinator)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self.coordinator.poll_enabled = last.state == "on"
            if self.coordinator.data is not None:
                self.coordinator._apply_scan_interval(self.coordinator.data)

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.poll_enabled)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.coordinator.poll_enabled = True
        if self.coordinator.data is not None:
            self.coordinator._apply_scan_interval(self.coordinator.data)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.coordinator.poll_enabled = False
        self.coordinator.update_interval = None
        self.async_write_ha_state()


async def _async_send_switch_command(
    coordinator: CheryEuropeDataUpdateCoordinator,
    entry: ConfigEntry,
    vin: str | None,
    kwargs: dict[str, Any],
    *,
    command_id: str,
    enabled: bool,
    start_minutes: int | None = None,
    duration_hours: int | None = None,
) -> None:
    extra: dict[str, Any] = {"enabled": enabled}
    if start_minutes is not None:
        extra["start_minutes"] = start_minutes
    if duration_hours is not None:
        extra["duration_hours"] = duration_hours
    await async_send_vehicle_command(
        coordinator,
        entry,
        vin,
        kwargs,
        command_id=command_id,
        **extra,
    )


class CheryEuropeChargeSwitch(CheryEuropeEntity, SwitchEntity, RestoreEntity):
    """Start or stop immediate charging through chargeStartStopControl."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the immediate charging switch."""
        super().__init__(coordinator, CHARGING_SWITCH_DESCRIPTION, entry)
        self._optimistic: bool | None = None
        self._restored: bool | None = None
        self._attr_unique_id = stable_unique_id(entry, CHARGING_SWITCH_DESCRIPTION.key, coordinator)

    async def async_added_to_hass(self) -> None:
        """Restore the last known charging switch state."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self._restored = last.state == "on"

    @property
    def is_on(self) -> bool | None:  # type: ignore[reportIncompatibleVariableOverride]
        """Return charging state from telemetry, optimistic update, or restore."""
        if self._optimistic is not None:
            return self._optimistic
        if self.chery_data.is_charging is not None:
            return self.chery_data.is_charging
        return self._restored

    @property
    def assumed_state(self) -> bool:  # type: ignore[reportIncompatibleVariableOverride]
        """Return true when no reliable charging state is available."""
        return self.is_on is None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start immediate charging."""
        self._optimistic = True
        self.async_write_ha_state()
        await _async_send_switch_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            kwargs,
            command_id="ve_1201",
            enabled=True,
        )
        self._optimistic = None
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop immediate charging."""
        self._optimistic = False
        self.async_write_ha_state()
        await _async_send_switch_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            kwargs,
            command_id="ve_1201",
            enabled=False,
        )
        self._optimistic = None
        self.async_write_ha_state()


class CheryEuropeScheduledChargeSwitch(CheryEuropeEntity, SwitchEntity, RestoreEntity):
    """Enable or disable scheduled charging through chargeAppointControl."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the scheduled charging switch."""
        super().__init__(coordinator, SCHEDULED_CHARGING_SWITCH_DESCRIPTION, entry)
        self._optimistic: bool | None = None
        self._restored: bool | None = None
        self._attr_unique_id = stable_unique_id(
            entry, SCHEDULED_CHARGING_SWITCH_DESCRIPTION.key, coordinator
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last known scheduled charging switch state."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self._restored = last.state == "on"

    @property
    def is_on(self) -> bool | None:  # type: ignore[reportIncompatibleVariableOverride]
        """Return whether the scheduled charging plan is enabled on the vehicle."""
        if self._optimistic is not None:
            return self._optimistic
        if self.chery_data.scheduled_charge_enabled is not None:
            return self.chery_data.scheduled_charge_enabled
        return self._restored

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the plan reported by the vehicle when available."""
        plan = self.chery_data.charge_appoint_plan
        if plan is None:
            return None
        attrs: dict[str, Any] = {}
        start = plan_start_time(plan)
        if start is not None:
            attrs["vehicle_start_time"] = f"{start.hour:02d}:{start.minute:02d}"
        hours = plan_duration_hours(plan)
        if hours is not None:
            attrs["vehicle_duration_hours"] = hours
        days = plan.get("cycleData")
        if isinstance(days, list) and days:
            attrs["vehicle_days"] = days
        return attrs or None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable scheduled charging with the configured start time and duration."""
        self._optimistic = True
        self.async_write_ha_state()
        await _async_send_switch_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            kwargs,
            command_id="ve_1202",
            enabled=True,
            start_minutes=self.coordinator.charge_start_minutes,
            duration_hours=self.coordinator.charge_duration_hours,
        )
        self._optimistic = None
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable scheduled charging."""
        self._optimistic = False
        self.async_write_ha_state()
        await _async_send_switch_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            kwargs,
            command_id="ve_1202",
            enabled=False,
            start_minutes=self.coordinator.charge_start_minutes,
            duration_hours=self.coordinator.charge_duration_hours,
        )
        self._optimistic = None
        self.async_write_ha_state()


class CheryEuropeDepartureSwitch(CheryEuropeEntity, SwitchEntity, RestoreEntity):
    """Arm the managed preparation plan so the car leaves at that time."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the departure switch."""
        super().__init__(coordinator, DEPARTURE_SWITCH_DESCRIPTION, entry)
        self._attr_unique_id = stable_unique_id(
            entry, DEPARTURE_SWITCH_DESCRIPTION.key, coordinator
        )
        self._armed_commanded = False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose that the state came from a command, so a reload keeps it."""
        if not self._armed_commanded:
            return None
        return {"armed_commanded": True}

    async def async_added_to_hass(self) -> None:
        """Restore the arm state; the car cannot be read back.

        A restored ``off`` is only believed when it was commanded from here,
        which the ``armed_commanded`` attribute records. Anything else is a
        leftover of the days when this switch defaulted to off, and the plan in
        the car is the one the owner armed in the app.
        """
        await super().async_added_to_hass()
        if self.coordinator.departure_armed is not None:
            return
        last = await self.async_get_last_state()
        if last is None:
            self.coordinator.departure_armed = True
            self.async_write_ha_state()
            return
        commanded = bool((last.attributes or {}).get("armed_commanded"))
        if last.state == "on":
            self._armed_commanded = commanded
            self.coordinator.departure_armed = True
        elif commanded:
            self._armed_commanded = True
            self.coordinator.departure_armed = False
        else:
            self.coordinator.departure_armed = True
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return whether the departure plan is armed."""
        return departure_state(self.coordinator)[1]

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Arm the departure plan, creating it from the configured time."""
        await async_set_departure(self.coordinator, self._entry, enabled=True)
        self._armed_commanded = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disarm the departure plan without deleting it."""
        await async_set_departure(self.coordinator, self._entry, enabled=False)
        self._armed_commanded = True
        self.async_write_ha_state()


class CheryEuropeDepartureDaySwitch(CheryEuropeEntity, SwitchEntity):
    """One weekday of the managed departure plan.

    The weekday list travels with the plan on every write, so toggling a day
    re-sends the whole plan (time, armed state and the new day list) to the car
    and is refused when it would leave the plan with no day at all.
    """

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: SwitchEntityDescription,
        entry: ConfigEntry,
        day: int,
    ) -> None:
        """Initialize the weekday switch."""
        super().__init__(coordinator, description, entry)
        self._day = day
        self._attr_translation_key = description.translation_key
        self._attr_unique_id = stable_unique_id(entry, description.key, coordinator)

    @property
    def is_on(self) -> bool:
        """Return whether the departure plan repeats on this weekday."""
        return self._day in departure_days(self.coordinator)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Add this weekday to the plan and write it to the car."""
        await async_set_departure_days(self.coordinator, self._entry, add=[self._day])
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Drop this weekday from the plan and write it to the car."""
        await async_set_departure_days(self.coordinator, self._entry, remove=[self._day])
        self.async_write_ha_state()
