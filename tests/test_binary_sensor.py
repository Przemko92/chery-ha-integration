"""Tests for the warning-flag binary sensors built from the status payload."""

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.chery_europe.binary_sensor import (
    BINARY_SENSOR_DESCRIPTIONS,
    CheryEuropeBinarySensor,
)
from custom_components.chery_europe.coordinator import CheryEuropeDataUpdateCoordinator
from custom_components.chery_europe.data import CheryData

VIN = "VIN123"

#: binary sensor key -> CheryData field carrying the car's own warning flag.
WARNING_FLAGS = {
    "alert_tire_front_left": "alert_tire_front_left",
    "alert_tire_front_right": "alert_tire_front_right",
    "alert_tire_rear_left": "alert_tire_rear_left",
    "alert_tire_rear_right": "alert_tire_rear_right",
    "alert_soc_low": "alert_soc_low",
    "alert_oil_service": "alert_oil_service",
    "alert_electricity": "alert_electricity",
}


@pytest.mark.parametrize("key", sorted(WARNING_FLAGS))
def test_warning_flag_follows_the_car_flag(key):
    """The *Call fields of the status payload must drive the problem sensors."""
    description = next(desc for desc in BINARY_SENSOR_DESCRIPTIONS if desc.key == key)
    field = WARNING_FLAGS[key]

    assert description.device_class is BinarySensorDeviceClass.PROBLEM
    assert description.value_fn(CheryData(vin=VIN, **{field: True})) is True
    assert description.value_fn(CheryData(vin=VIN, **{field: False})) is False
    assert description.value_fn(CheryData(vin=VIN)) is None


def test_warning_flag_entity_reports_problem_state():
    """A raised flag has to surface as an on state on the entity itself."""
    coordinator = SimpleNamespace(
        data=CheryData(vin=VIN, alert_electricity=True),
        last_update_success=True,
    )
    entry = SimpleNamespace(entry_id="entry-1", options={})
    description = next(
        desc for desc in BINARY_SENSOR_DESCRIPTIONS if desc.key == "alert_electricity"
    )
    entity = CheryEuropeBinarySensor(coordinator, description, entry)

    assert entity.is_on is True
    assert entity.device_class is BinarySensorDeviceClass.PROBLEM
