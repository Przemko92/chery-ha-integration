# pyright: reportArgumentType=false, reportOptionalSubscript=false, reportTypedDictNotRequiredAccess=false

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.const import PERCENTAGE

from custom_components.chery_europe.const import DOMAIN
from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.sensor import (
    SENSOR_DESCRIPTIONS,
    TIMESTAMP_SENSOR_DESCRIPTIONS,
    CheryEuropeSensor,
    CheryEuropeTimestampSensor,
)


def _entry(entry_id="entry-1"):
    return SimpleNamespace(entry_id=entry_id)


def _coordinator(data, last_update_success=True):
    return SimpleNamespace(data=data, last_update_success=last_update_success)


def _sensor(key, data, entry=None, last_update_success=True):
    description = next(desc for desc in SENSOR_DESCRIPTIONS if desc.key == key)
    return CheryEuropeSensor(
        _coordinator(data, last_update_success=last_update_success),
        description,
        entry or _entry(),
    )


def test_sensor_values_are_read_from_coordinator_data():
    data = CheryData(
        vin="VIN123",
        battery_level=91,
        tire_pressures={"front_left": 2.4},
        last_updated="2026-06-15T12:00:00Z",
    )

    battery = _sensor("battery_level", data)
    tire = _sensor("tire_pressure_front_left", data)

    assert battery.native_value == 91
    assert tire.native_value == 2.4
    assert battery.extra_state_attributes == {
        "last_updated": "2026-06-15T12:00:00Z",
    }


def test_vehicle_speed_sensor_reads_from_coordinator_data():
    data = CheryData(vin="VIN123", gps_speed=38.0)
    sensor = _sensor("vehicle_speed", data)

    assert sensor.native_value == 38.0


def test_fuel_level_sensor_uses_percentage_unit():
    """oilSurplus from the API is tank fill percentage, not liters."""
    description = next(desc for desc in SENSOR_DESCRIPTIONS if desc.key == "fuel_level")
    sensor = _sensor("fuel_level", CheryData(vin="VIN123", fuel_level=67.0))

    assert description.native_unit_of_measurement == PERCENTAGE
    assert sensor.native_value == 67.0
    assert sensor.native_unit_of_measurement == PERCENTAGE


def test_timestamp_sensor_reads_result_time_from_coordinator_data():
    data = CheryData(
        vin="VIN123",
        last_updated="2026-06-15T12:00:00+00:00",
    )
    description = TIMESTAMP_SENSOR_DESCRIPTIONS[0]
    sensor = CheryEuropeTimestampSensor(
        _coordinator(data),
        description,
        _entry(),
    )

    value = sensor.native_value

    assert value is not None
    assert value.isoformat() == "2026-06-15T12:00:00+00:00"


def test_sensor_is_unavailable_when_coordinator_data_is_missing():
    sensor = _sensor("battery_level", None)

    assert sensor.available is False
    assert sensor.native_value is None


def test_sensor_device_info_uses_vehicle_vin_and_chery_metadata():
    sensor = _sensor("battery_level", CheryData(vin="VIN123"), _entry("fallback-entry"))

    device_info = sensor.device_info

    assert device_info["identifiers"] == {(DOMAIN, "VIN123")}
    assert device_info["manufacturer"] == "Chery"
    assert device_info["name"] == "Chery Vehicle"
    assert sensor.unique_id == "VIN123_battery_level"
