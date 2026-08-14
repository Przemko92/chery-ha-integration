# pyright: reportIncompatibleVariableOverride=false

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import CheryData
from .entity import CheryEuropeEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class CheryEuropeBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes a Chery Europe vehicle binary sensor."""

    value_fn: Callable[[CheryData], bool | None]


BINARY_SENSOR_DESCRIPTIONS: tuple[CheryEuropeBinarySensorEntityDescription, ...] = (
    CheryEuropeBinarySensorEntityDescription(
        key="online",
        name="Online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.online,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="charging",
        name="Charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data.is_charging,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="appointment_charging",
        name="Scheduled charging",
        translation_key="appointment_charging",
        icon="mdi:calendar-clock",
        value_fn=lambda data: data.appointment_charge,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="charge_gun_connected",
        name="Charge cable connected",
        translation_key="charge_gun_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda data: data.charge_gun_connected,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="fast_charge_gun_connected",
        name="Fast charger connected",
        translation_key="fast_charge_gun_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda data: data.fast_charge_gun_connected,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="engine",
        name="Engine",
        translation_key="engine",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda data: data.engine_on,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="high_voltage",
        name="High voltage system",
        translation_key="high_voltage",
        icon="mdi:flash",
        value_fn=lambda data: data.hv_high_voltage_on,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="steering_wheel_heating",
        name="Steering wheel heating",
        translation_key="steering_wheel_heating",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda data: data.steering_wheel_heating,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="air_purification",
        name="Air purification",
        translation_key="air_purification",
        icon="mdi:air-filter",
        value_fn=lambda data: data.air_purification,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="sunroof",
        name="Sunroof",
        translation_key="sunroof",
        icon="mdi:car-select",
        value_fn=lambda data: data.sunroof_open,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="door_front_left",
        name="Front left door",
        translation_key="door_front_left",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: data.door_front_left_open,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="door_front_right",
        name="Front right door",
        translation_key="door_front_right",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: data.door_front_right_open,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="door_rear_left",
        name="Rear left door",
        translation_key="door_rear_left",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: data.door_rear_left_open,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="door_rear_right",
        name="Rear right door",
        translation_key="door_rear_right",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: data.door_rear_right_open,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="trunk",
        name="Trunk",
        translation_key="trunk",
        device_class=BinarySensorDeviceClass.DOOR,
        value_fn=lambda data: data.trunk_open,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="window_front_left",
        name="Front left window",
        translation_key="window_front_left",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda data: data.window_front_left_open,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="window_front_right",
        name="Front right window",
        translation_key="window_front_right",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda data: data.window_front_right_open,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="window_rear_left",
        name="Rear left window",
        translation_key="window_rear_left",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda data: data.window_rear_left_open,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="window_rear_right",
        name="Rear right window",
        translation_key="window_rear_right",
        device_class=BinarySensorDeviceClass.WINDOW,
        value_fn=lambda data: data.window_rear_right_open,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="driver_seat_heating",
        name="Driver seat heating",
        translation_key="driver_seat_heating",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda data: data.driver_seat_heating,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="passenger_seat_heating",
        name="Passenger seat heating",
        translation_key="passenger_seat_heating",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda data: data.passenger_seat_heating,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="driver_seat_ventilation",
        name="Driver seat ventilation",
        translation_key="driver_seat_ventilation",
        icon="mdi:car-seat-cooler",
        value_fn=lambda data: data.driver_seat_ventilation,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="passenger_seat_ventilation",
        name="Passenger seat ventilation",
        translation_key="passenger_seat_ventilation",
        icon="mdi:car-seat-cooler",
        value_fn=lambda data: data.passenger_seat_ventilation,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe binary sensors from a config entry."""
    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        CheryEuropeBinarySensor(coordinator, description, entry)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class CheryEuropeBinarySensor(CheryEuropeEntity, BinarySensorEntity):
    """Representation of a Chery Europe vehicle binary sensor."""

    entity_description: CheryEuropeBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: CheryEuropeBinarySensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the binary sensor state from coordinator data."""
        if self.coordinator.data is None:
            return None
        try:
            return self.entity_description.value_fn(self.chery_data)
        except (KeyError, TypeError, ValueError, AttributeError):
            return None
