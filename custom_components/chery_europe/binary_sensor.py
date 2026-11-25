# pyright: reportIncompatibleVariableOverride=false

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .alerts import collect_warnings
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import CheryData
from .entity import CheryEuropeEntity, iter_entry_coordinators, stable_unique_id

PARALLEL_UPDATES = 0


def _any_warning(data: CheryData) -> bool | None:
    """Return True when any of the car's own warning flags is raised.

    The aggregate stays unknown only while the car reported none of the flags.
    """
    flags = (
        data.alert_tire_front_left,
        data.alert_tire_front_right,
        data.alert_tire_rear_left,
        data.alert_tire_rear_right,
        data.alert_soc_low,
        data.alert_oil_service,
        data.alert_electricity,
    )
    if any(flag is True for flag in flags):
        return True
    if all(flag is None for flag in flags):
        return None
    return False


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
        key="air_purification",
        name="Air purification",
        translation_key="air_purification",
        icon="mdi:air-filter",
        value_fn=lambda data: data.air_purification,
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
    # Disabled by default: the Chery Europe backend does not report the bonnet
    # at all. A live status frame (~87 fields) carries no hood/bonnet field under
    # any name -- only engineState, trunkDoor, liftgateOperateState, the four
    # doors, the windows and the sunroof -- so value_fn always resolves to None
    # and the entity would sit at "unknown" forever. Kept for models whose
    # backend does send the field: enable it manually if yours does.
    CheryEuropeBinarySensorEntityDescription(
        key="hood",
        name="Hood",
        translation_key="hood",
        device_class=BinarySensorDeviceClass.OPENING,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.hood_open,
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
    # The car's own warning flags (the ``*Call`` fields of the status payload).
    # They only say "something is wrong", the measured value stays in the
    # matching sensor (tire pressure, battery level, ...).
    CheryEuropeBinarySensorEntityDescription(
        key="info",
        name="Info",
        translation_key="info",
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:car-info",
        value_fn=_any_warning,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="alert_tire_front_left",
        name="Front left tire",
        translation_key="alert_tire_front_left",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.alert_tire_front_left,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="alert_tire_front_right",
        name="Front right tire",
        translation_key="alert_tire_front_right",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.alert_tire_front_right,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="alert_tire_rear_left",
        name="Rear left tire",
        translation_key="alert_tire_rear_left",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.alert_tire_rear_left,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="alert_tire_rear_right",
        name="Rear right tire",
        translation_key="alert_tire_rear_right",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.alert_tire_rear_right,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="alert_soc_low",
        name="Low state of charge",
        translation_key="alert_soc_low",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.alert_soc_low,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="alert_oil_service",
        name="Oil service due",
        translation_key="alert_oil_service",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.alert_oil_service,
    ),
    CheryEuropeBinarySensorEntityDescription(
        key="alert_electricity",
        name="Electrical system warning",
        translation_key="alert_electricity",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.alert_electricity,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe binary sensors from a config entry."""
    async_add_entities(
        [
            CheryEuropeBinarySensor(coordinator, description, entry)
            for coordinator in iter_entry_coordinators(entry)
            for description in BINARY_SENSOR_DESCRIPTIONS
        ]
    )


class CheryEuropeBinarySensor(CheryEuropeEntity, BinarySensorEntity, RestoreEntity):
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
        self._attr_unique_id = stable_unique_id(entry, description.key, coordinator)
        self._restored: bool | None = None
        self._last_known: bool | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in ("on", "off"):
            self._restored = last.state == "on"

    @property
    def is_on(self) -> bool | None:
        """Return the binary sensor state from coordinator data."""
        live = None
        if self.coordinator.data is not None:
            try:
                live = self.entity_description.value_fn(self.chery_data)
            except (KeyError, TypeError, ValueError, AttributeError):
                live = None
        if live is not None:
            self._last_known = live
            return live
        if self._last_known is not None:
            return self._last_known
        return self._restored

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the active warnings behind the aggregate sensor."""
        if self.entity_description.key != "info" or self.coordinator.data is None:
            return {}
        warnings = collect_warnings(
            self.chery_data, getattr(self.hass.config, "language", None)
        )
        return {
            "count": len(warnings),
            "categories": sorted({alert.category for alert in warnings}),
            "alerts": [alert.as_dict() for alert in warnings],
        }
