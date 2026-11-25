# pyright: reportArgumentType=false, reportOptionalSubscript=false, reportTypedDictNotRequiredAccess=false

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
)

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


def test_traction_battery_sensors_read_from_coordinator_data():
    data = CheryData(
        vin="VIN123",
        charging_power_kw=6.6,
        battery_voltage_v=323.1,
        battery_current_a=-12.5,
    )
    power = next(desc for desc in SENSOR_DESCRIPTIONS if desc.key == "charging_power_kw")
    voltage = next(desc for desc in SENSOR_DESCRIPTIONS if desc.key == "battery_voltage_v")
    current = next(desc for desc in SENSOR_DESCRIPTIONS if desc.key == "battery_current_a")

    assert _sensor("charging_power_kw", data).native_value == 6.6
    assert power.device_class == SensorDeviceClass.POWER
    assert power.native_unit_of_measurement == UnitOfPower.KILO_WATT
    assert power.translation_key == "charging_power_kw"
    assert _sensor("battery_voltage_v", data).native_value == 323.1
    assert voltage.device_class == SensorDeviceClass.VOLTAGE
    assert voltage.native_unit_of_measurement == UnitOfElectricPotential.VOLT
    assert _sensor("battery_current_a", data).native_value == -12.5
    assert current.device_class == SensorDeviceClass.CURRENT
    assert current.native_unit_of_measurement == UnitOfElectricCurrent.AMPERE


def test_remaining_charge_time_shows_zero_instead_of_the_previous_value():
    sensor = _sensor(
        "remain_charge_time",
        CheryData(vin="VIN123", remain_charge_time_min=0.0),
    )
    sensor._last_known = 4.0

    assert sensor.native_value == 0.0


def test_fuel_level_sensor_uses_percentage_unit():
    """oilSurplus from the API is tank fill percentage, not liters."""
    description = next(desc for desc in SENSOR_DESCRIPTIONS if desc.key == "fuel_level")
    sensor = _sensor("fuel_level", CheryData(vin="VIN123", fuel_level=67.0))

    assert description.native_unit_of_measurement == PERCENTAGE
    assert sensor.native_value == 67.0
    assert sensor.native_unit_of_measurement == PERCENTAGE


def test_tire_pressure_sensors_use_pressure_device_class():
    """Bar stays the native unit so Home Assistant can offer psi."""
    keys = (
        "tire_pressure_front_left",
        "tire_pressure_front_right",
        "tire_pressure_rear_left",
        "tire_pressure_rear_right",
    )
    by_key = {desc.key: desc for desc in SENSOR_DESCRIPTIONS}

    for key in keys:
        assert by_key[key].device_class == SensorDeviceClass.PRESSURE
        assert by_key[key].native_unit_of_measurement == UnitOfPressure.BAR


def test_numeric_sensors_have_long_term_statistics_state_class():
    """Numeric vehicle sensors must declare state_class so HA records LTS."""
    expected = {
        "battery_level": SensorStateClass.MEASUREMENT,
        "charging_power_kw": SensorStateClass.MEASUREMENT,
        "battery_voltage_v": SensorStateClass.MEASUREMENT,
        "battery_current_a": SensorStateClass.MEASUREMENT,
        "fuel_level": SensorStateClass.MEASUREMENT,
        "range": SensorStateClass.MEASUREMENT,
        "tire_pressure_front_left": SensorStateClass.MEASUREMENT,
        "tire_pressure_front_right": SensorStateClass.MEASUREMENT,
        "tire_pressure_rear_left": SensorStateClass.MEASUREMENT,
        "tire_pressure_rear_right": SensorStateClass.MEASUREMENT,
        "odometer": SensorStateClass.TOTAL_INCREASING,
        "electric_range": SensorStateClass.MEASUREMENT,
        "electric_odometer": SensorStateClass.TOTAL_INCREASING,
        "vehicle_speed": SensorStateClass.MEASUREMENT,
        "fuel_range": SensorStateClass.MEASUREMENT,
        "power_consumption": SensorStateClass.MEASUREMENT,
        "fuel_consumption": SensorStateClass.MEASUREMENT,
        "remain_charge_time": SensorStateClass.MEASUREMENT,
        "tire_temperature_front_left": SensorStateClass.MEASUREMENT,
        "tire_temperature_front_right": SensorStateClass.MEASUREMENT,
        "tire_temperature_rear_left": SensorStateClass.MEASUREMENT,
        "tire_temperature_rear_right": SensorStateClass.MEASUREMENT,
        "exterior_temperature": SensorStateClass.MEASUREMENT,
        "interior_temperature": SensorStateClass.MEASUREMENT,
    }
    by_key = {desc.key: desc.state_class for desc in SENSOR_DESCRIPTIONS}

    assert {key: by_key[key] for key in expected} == expected


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

    assert device_info["identifiers"] == {(DOMAIN, "fallback-entry")}
    assert device_info["manufacturer"] == "Chery"
    assert device_info["name"] == "Chery Vehicle"
    assert device_info["serial_number"] == "VIN123"
    assert sensor.unique_id == "fallback-entry_battery_level"
    assert "VIN123" not in sensor.unique_id


def test_exterior_temperature_reads_the_status_payload():
    """outsideTemperature from the status document drives the outside sensor."""
    description = next(
        desc for desc in SENSOR_DESCRIPTIONS if desc.key == "exterior_temperature"
    )
    sensor = _sensor(
        "exterior_temperature", CheryData(vin="VIN123", exterior_temperature=7.5)
    )

    assert sensor.native_value == 7.5
    assert sensor.device_class == SensorDeviceClass.TEMPERATURE
    assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS
    assert description.state_class == SensorStateClass.MEASUREMENT
    assert _sensor("exterior_temperature", CheryData(vin="VIN123")).native_value is None


def test_interior_temperature_reads_the_cabin_temperature():
    """The cabin field is exposed on its own, next to the climate entity."""
    sensor = _sensor(
        "interior_temperature", CheryData(vin="VIN123", interior_temperature=21.5)
    )

    assert sensor.native_value == 21.5
    assert sensor.device_class == SensorDeviceClass.TEMPERATURE
    assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS
    assert _sensor("interior_temperature", CheryData(vin="VIN123")).native_value is None


def test_interior_temperature_is_disabled_after_install():
    """Off by default: the climate card already shows the cabin temperature."""
    sensor = _sensor("interior_temperature", CheryData(vin="VIN123"))

    assert sensor.entity_registry_enabled_default is False
    assert sensor.entity_category is None
