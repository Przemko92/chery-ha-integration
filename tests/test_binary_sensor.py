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


def test_info_aggregate_follows_any_flag():
    """The aggregate is on when any warning flag is raised, off when all are clear."""
    description = next(desc for desc in BINARY_SENSOR_DESCRIPTIONS if desc.key == "info")

    assert description.device_class is BinarySensorDeviceClass.PROBLEM
    assert description.value_fn(CheryData(vin=VIN)) is None
    assert description.value_fn(CheryData(vin=VIN, alert_tire_rear_left=False)) is False
    assert (
        description.value_fn(
            CheryData(vin=VIN, alert_tire_rear_left=False, alert_oil_service=True)
        )
        is True
    )
    # Door/window openings are informational and must not raise the aggregate.
    assert (
        description.value_fn(CheryData(vin=VIN, alert_soc_low=False, door_front_left_open=True))
        is False
    )


def test_info_aggregate_entity_lists_active_warnings():
    """The aggregate exposes the raised flags as attributes."""
    coordinator = SimpleNamespace(
        data=CheryData(vin=VIN, alert_tire_front_left=True, alert_oil_service=False),
        last_update_success=True,
    )
    entry = SimpleNamespace(entry_id="entry-1", options={})
    description = next(desc for desc in BINARY_SENSOR_DESCRIPTIONS if desc.key == "info")
    entity = CheryEuropeBinarySensor(coordinator, description, entry)
    entity.hass = SimpleNamespace(config=SimpleNamespace(language="pl"))

    assert entity.is_on is True
    attributes = entity.extra_state_attributes

    assert attributes["count"] == 1
    assert attributes["categories"] == ["tyre"]
    assert attributes["alerts"][0]["text"] == "Niskie ciśnienie w oponie: przednia lewa"
