# pyright: reportIncompatibleVariableOverride=false

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfPressure, UnitOfSpeed, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import CheryData
from .entity import CheryEuropeEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class CheryEuropeSensorEntityDescription(SensorEntityDescription):
    """Describes a Chery Europe vehicle sensor."""

    value_fn: Callable[[CheryData], StateType]


SENSOR_DESCRIPTIONS: tuple[CheryEuropeSensorEntityDescription, ...] = (
    CheryEuropeSensorEntityDescription(
        key="battery_level",
        name="Battery level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.battery_level,
    ),
    CheryEuropeSensorEntityDescription(
        key="fuel_level",
        name="Fuel remaining",
        translation_key="fuel_level",
        icon="mdi:fuel",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: data.fuel_level,
    ),
    CheryEuropeSensorEntityDescription(
        key="range",
        name="Range",
        translation_key="range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda data: data.range_km,
    ),
    CheryEuropeSensorEntityDescription(
        key="tire_pressure_front_left",
        name="Front left tire pressure",
        translation_key="tire_pressure_front_left",
        icon="mdi:car-tire-alert",
        native_unit_of_measurement=UnitOfPressure.BAR,
        value_fn=lambda data: _tire_pressure(data, "front_left"),
    ),
    CheryEuropeSensorEntityDescription(
        key="tire_pressure_front_right",
        name="Front right tire pressure",
        translation_key="tire_pressure_front_right",
        icon="mdi:car-tire-alert",
        native_unit_of_measurement=UnitOfPressure.BAR,
        value_fn=lambda data: _tire_pressure(data, "front_right"),
    ),
    CheryEuropeSensorEntityDescription(
        key="tire_pressure_rear_left",
        name="Rear left tire pressure",
        translation_key="tire_pressure_rear_left",
        icon="mdi:car-tire-alert",
        native_unit_of_measurement=UnitOfPressure.BAR,
        value_fn=lambda data: _tire_pressure(data, "rear_left"),
    ),
    CheryEuropeSensorEntityDescription(
        key="tire_pressure_rear_right",
        name="Rear right tire pressure",
        translation_key="tire_pressure_rear_right",
        icon="mdi:car-tire-alert",
        native_unit_of_measurement=UnitOfPressure.BAR,
        value_fn=lambda data: _tire_pressure(data, "rear_right"),
    ),
    CheryEuropeSensorEntityDescription(
        key="odometer",
        name="Odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:counter",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda data: data.odometer_km,
    ),
    CheryEuropeSensorEntityDescription(
        key="electric_range",
        name="Electric range",
        translation_key="electric_range",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:car-electric",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda data: data.electric_range_km,
    ),
    CheryEuropeSensorEntityDescription(
        key="electric_odometer",
        name="Electric odometer",
        translation_key="electric_odometer",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:car-electric-outline",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.electric_odometer_km,
    ),
    CheryEuropeSensorEntityDescription(
        key="vehicle_speed",
        name="Vehicle speed",
        translation_key="vehicle_speed",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        value_fn=lambda data: data.gps_speed,
    ),
    CheryEuropeSensorEntityDescription(
        key="fuel_range",
        name="Fuel range",
        translation_key="fuel_range",
        device_class=SensorDeviceClass.DISTANCE,
        icon="mdi:gas-station",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda data: data.fuel_range_km,
    ),
    CheryEuropeSensorEntityDescription(
        key="power_consumption",
        name="Power consumption",
        translation_key="power_consumption",
        icon="mdi:flash",
        native_unit_of_measurement="kWh/100km",
        value_fn=lambda data: data.power_consumption_kwh_100km,
    ),
    CheryEuropeSensorEntityDescription(
        key="fuel_consumption",
        name="Fuel consumption",
        translation_key="fuel_consumption",
        icon="mdi:gas-station",
        native_unit_of_measurement="L/100km",
        value_fn=lambda data: data.average_fuel_consumption,
    ),
    CheryEuropeSensorEntityDescription(
        key="remain_charge_time",
        name="Remaining charge time",
        translation_key="remain_charge_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-sand",
        value_fn=lambda data: data.remain_charge_time_min,
    ),
    CheryEuropeSensorEntityDescription(
        key="charge_status",
        name="Charge status",
        translation_key="charge_status",
        device_class=SensorDeviceClass.ENUM,
        options=["not_charging", "charging", "charge_complete"],
        icon="mdi:ev-station",
        value_fn=lambda data: data.charge_status,
    ),
    CheryEuropeSensorEntityDescription(
        key="appointment_charge_status",
        name="Scheduled charging status",
        translation_key="appointment_charge_status",
        device_class=SensorDeviceClass.ENUM,
        options=["off", "enabled", "running"],
        icon="mdi:calendar-clock",
        value_fn=lambda data: data.appointment_charge_status,
    ),
    CheryEuropeSensorEntityDescription(
        key="vehicle_nickname",
        name="Vehicle nickname",
        translation_key="vehicle_nickname",
        icon="mdi:car-key",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.vehicle_nickname,
    ),
    CheryEuropeSensorEntityDescription(
        key="vehicle_full_name",
        name="Vehicle model",
        translation_key="vehicle_full_name",
        icon="mdi:car-info",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.vehicle_full_name,
    ),
    CheryEuropeSensorEntityDescription(
        key="vehicle_color",
        name="Vehicle color",
        translation_key="vehicle_color",
        icon="mdi:palette",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.vehicle_color_name_en,
    ),
    CheryEuropeSensorEntityDescription(
        key="vehicle_picture",
        name="Vehicle picture",
        translation_key="vehicle_picture",
        icon="mdi:car",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.vehicle_picture_url,
    ),
    CheryEuropeSensorEntityDescription(
        key="climate_min_temperature",
        name="Climate minimum temperature",
        translation_key="climate_min_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.min_temperature,
    ),
    CheryEuropeSensorEntityDescription(
        key="climate_max_temperature",
        name="Climate maximum temperature",
        translation_key="climate_max_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.max_temperature,
    ),
    CheryEuropeSensorEntityDescription(
        key="tire_temperature_front_left",
        name="Front left tire temperature",
        translation_key="tire_temperature_front_left",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: _tire_temperature(data, "front_left"),
    ),
    CheryEuropeSensorEntityDescription(
        key="tire_temperature_front_right",
        name="Front right tire temperature",
        translation_key="tire_temperature_front_right",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: _tire_temperature(data, "front_right"),
    ),
    CheryEuropeSensorEntityDescription(
        key="tire_temperature_rear_left",
        name="Rear left tire temperature",
        translation_key="tire_temperature_rear_left",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: _tire_temperature(data, "rear_left"),
    ),
    CheryEuropeSensorEntityDescription(
        key="tire_temperature_rear_right",
        name="Rear right tire temperature",
        translation_key="tire_temperature_rear_right",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: _tire_temperature(data, "rear_right"),
    ),
)

TIMESTAMP_SENSOR_DESCRIPTIONS: tuple[CheryEuropeSensorEntityDescription, ...] = (
    CheryEuropeSensorEntityDescription(
        key="last_data_update",
        name="Last data update",
        translation_key="last_data_update",
        icon="mdi:database-clock",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_updated,
    ),
)

STATUS_SENSOR_DESCRIPTIONS: tuple[CheryEuropeSensorEntityDescription, ...] = (
    CheryEuropeSensorEntityDescription(
        key="command_status",
        name="Command result",
        translation_key="command_status",
        icon="mdi:car-cog",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.command_status,
    ),
    CheryEuropeSensorEntityDescription(
        key="wake_status",
        name="Wake result",
        translation_key="wake_status",
        icon="mdi:car-connected",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.wake_status,
    ),
    CheryEuropeSensorEntityDescription(
        key="probe_status",
        name="Position probe result",
        translation_key="probe_status",
        icon="mdi:crosshairs-gps",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.probe_status,
    ),
)


def _tire_pressure(data: CheryData, key: str) -> float | None:
    """Return a tire pressure by normalized tire position key."""
    if data.tire_pressures is None:
        return None
    return data.tire_pressures.get(key)


def _tire_temperature(data: CheryData, key: str) -> float | None:
    """Return a tire temperature by normalized tire position key."""
    if data.tire_temperatures is None:
        return None
    return data.tire_temperatures.get(key)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe sensors from a config entry."""
    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    entities = [
        CheryEuropeSensor(coordinator, description, entry)
        for description in SENSOR_DESCRIPTIONS
    ]
    entities.extend(
        CheryEuropeStatusSensor(coordinator, description, entry)
        for description in STATUS_SENSOR_DESCRIPTIONS
    )
    entities.extend(
        CheryEuropeTimestampSensor(coordinator, description, entry)
        for description in TIMESTAMP_SENSOR_DESCRIPTIONS
    )
    async_add_entities(entities)


class _CheryEuropeRestoreSensor(CheryEuropeEntity, RestoreSensor):
    """Sensor that keeps the last known value across HA restarts."""

    entity_description: CheryEuropeSensorEntityDescription
    _restored: StateType = None
    _last_known: StateType = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_sensor_data()
        if last is not None:
            self._restored = last.native_value

    def _live_value(self) -> StateType:
        if self.coordinator.data is None:
            return None
        try:
            return self.entity_description.value_fn(self.chery_data)
        except (KeyError, TypeError, ValueError, AttributeError):
            return None

    @property
    def native_value(self) -> StateType:
        live = self._live_value()
        if live is not None:
            self._last_known = live
            return live
        if self._last_known is not None:
            return self._last_known
        return self._restored


class CheryEuropeSensor(_CheryEuropeRestoreSensor):
    """Representation of a Chery Europe vehicle sensor."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: CheryEuropeSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the sensor value from coordinator data."""
        value = super().native_value
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @property
    def entity_picture(self) -> str | None:
        """Return the vehicle picture URL for the diagnostic picture sensor."""
        if self.entity_description.key != "vehicle_picture":
            return None
        return self.chery_data.vehicle_picture_url

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return vehicle metadata for this sensor."""
        return {
            "last_updated": self.chery_data.last_updated,
        }

    @property
    def available(self) -> bool:
        """Return if entity data is available."""
        return self.coordinator.data is not None and super().available


class CheryEuropeStatusSensor(_CheryEuropeRestoreSensor):
    """Diagnostic text sensor for command/wake/probe results."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: CheryEuropeSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}"


class CheryEuropeTimestampSensor(_CheryEuropeRestoreSensor):
    """Diagnostic timestamp sensor sourced from API resultTime."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _last_known_dt: datetime | None = None

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: CheryEuropeSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        restored = self._restored
        if isinstance(restored, str):
            restored = dt_util.parse_datetime(restored)
        if not (isinstance(restored, datetime) and restored.tzinfo is not None):
            restored = None
        self._restored = restored

    def _parse_timestamp(self, value: StateType) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            parsed = dt_util.parse_datetime(value)
        else:
            return None
        if parsed is None or parsed.tzinfo is None:
            return None
        return parsed

    @property
    def native_value(self) -> datetime | None:
        live = self._parse_timestamp(self._live_value())
        if live is not None:
            self._last_known_dt = live
            return live
        if self._last_known_dt is not None:
            return self._last_known_dt
        return self._parse_timestamp(self._restored)


# Backwards compatibility alias for tests and external consumers
SENSOR_TYPES = SENSOR_DESCRIPTIONS
