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

from .command_exec import async_send_vehicle_command
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import CheryData
from .entity import CheryEuropeEntity

PARALLEL_UPDATES = 0


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
    CheryEuropeSwitchEntityDescription(
        key="driver_seat_heating",
        name="Driver seat heating",
        translation_key="driver_seat_heating",
        icon="mdi:car-seat-heater",
        command_id="ve_1204",
        command_values={"seat_field": "mSeatHeating"},
        state_fn=lambda data: data.driver_seat_heating,
    ),
    CheryEuropeSwitchEntityDescription(
        key="passenger_seat_heating",
        name="Passenger seat heating",
        translation_key="passenger_seat_heating",
        icon="mdi:car-seat-heater",
        command_id="ve_1204",
        command_values={"seat_field": "pSeatHeating"},
        state_fn=lambda data: data.passenger_seat_heating,
    ),
    CheryEuropeSwitchEntityDescription(
        key="driver_seat_ventilation",
        name="Driver seat ventilation",
        translation_key="driver_seat_ventilation",
        icon="mdi:car-seat-cooler",
        command_id="ve_1204",
        command_values={"seat_field": "mSeatAiry"},
        state_fn=lambda data: data.driver_seat_ventilation,
    ),
    CheryEuropeSwitchEntityDescription(
        key="passenger_seat_ventilation",
        name="Passenger seat ventilation",
        translation_key="passenger_seat_ventilation",
        icon="mdi:car-seat-cooler",
        command_id="ve_1204",
        command_values={"seat_field": "pSeatAiry"},
        state_fn=lambda data: data.passenger_seat_ventilation,
    ),
    CheryEuropeSwitchEntityDescription(
        key="rear_left_seat_heating",
        name="Rear left seat heating",
        translation_key="rear_left_seat_heating",
        icon="mdi:car-seat-heater",
        command_id="ve_1204",
        command_values={"seat_field": "blSeatHeating"},
        state_fn=lambda data: data.rear_left_seat_heating,
    ),
    CheryEuropeSwitchEntityDescription(
        key="rear_right_seat_heating",
        name="Rear right seat heating",
        translation_key="rear_right_seat_heating",
        icon="mdi:car-seat-heater",
        command_id="ve_1204",
        command_values={"seat_field": "brSeatHeating"},
        state_fn=lambda data: data.rear_right_seat_heating,
    ),
    CheryEuropeSwitchEntityDescription(
        key="rear_left_seat_ventilation",
        name="Rear left seat ventilation",
        translation_key="rear_left_seat_ventilation",
        icon="mdi:car-seat-cooler",
        command_id="ve_1204",
        command_values={"seat_field": "blSeatAiry"},
        state_fn=lambda data: data.rear_left_seat_ventilation,
    ),
    CheryEuropeSwitchEntityDescription(
        key="rear_right_seat_ventilation",
        name="Rear right seat ventilation",
        translation_key="rear_right_seat_ventilation",
        icon="mdi:car-seat-cooler",
        command_id="ve_1204",
        command_values={"seat_field": "brSeatAiry"},
        state_fn=lambda data: data.rear_right_seat_ventilation,
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe switches from a config entry."""
    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    entities: list[SwitchEntity] = [
        CheryEuropeCommandSwitch(coordinator, description, entry)
        for description in SWITCH_DESCRIPTIONS
    ]
    entities.extend(
        [
            CheryEuropeChargeSwitch(coordinator, entry),
            CheryEuropeScheduledChargeSwitch(coordinator, entry),
            CheryEuropePollingSwitch(coordinator, entry),
        ]
    )
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
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}"

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
)


class CheryEuropePollingSwitch(CheryEuropeEntity, SwitchEntity, RestoreEntity):
    """Enable or disable automatic telemetry polling."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, POLLING_SWITCH_DESCRIPTION, entry)
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{POLLING_SWITCH_DESCRIPTION.key}"

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
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{CHARGING_SWITCH_DESCRIPTION.key}"

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
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{SCHEDULED_CHARGING_SWITCH_DESCRIPTION.key}"

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
    def assumed_state(self) -> bool:  # type: ignore[reportIncompatibleVariableOverride]
        """Return true when no reliable scheduled charging state is available."""
        return self.is_on is None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the plan reported by the vehicle when available."""
        plan = self.chery_data.charge_appoint_plan
        if plan is None:
            return None
        attrs: dict[str, Any] = {}
        try:
            minutes = int(plan["startTime"])
            if 0 <= minutes < 1440:
                attrs["vehicle_start_time"] = f"{minutes // 60:02d}:{minutes % 60:02d}"
        except (KeyError, TypeError, ValueError):
            pass
        try:
            attrs["vehicle_duration_hours"] = round(int(plan["timeConsuming"]) / 60, 1)
        except (KeyError, TypeError, ValueError):
            pass
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
