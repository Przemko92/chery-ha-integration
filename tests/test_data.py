# pyright: reportArgumentType=false, reportOptionalSubscript=false

"""Tests for CheryData.from_api_response normalization of HVAC/lock feedback fields."""

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.data import CheryData, apply_command_feedback, merge_chery_data, vehicle_display_name
from custom_components.chery_europe.types.vehicle_models import VehicleStatus


# ---------------------------------------------------------------------------
# Dict input — camelCase key variants
# ---------------------------------------------------------------------------


def test_dict_camelcase_keys_normalize_correctly():
    """camelCase API keys map to the canonical snake_case fields."""
    response = {
        "vin": "VIN123",
        "frontWindshieldHeating": True,
        "rearWindowDefrost": False,
        "hvacEnabled": True,
        "hvacMode": "auto",
        "targetTemperature": 22.5,
    }

    data = CheryData.from_api_response(response)

    assert data.vin == "VIN123"
    assert data.front_windshield_heating is True
    assert data.rear_window_defrost is False
    assert data.hvac_enabled is True
    assert data.hvac_mode == "auto"
    assert data.target_temperature == 22.5


def test_dict_snake_case_keys_normalize_correctly():
    """snake_case API keys map to the canonical fields."""
    response = {
        "front_windshield_heating": True,
        "rear_window_defrost": True,
        "hvac_enabled": False,
        "hvac_mode": "cool",
        "target_temperature": 18.0,
    }

    data = CheryData.from_api_response(response)

    assert data.front_windshield_heating is True
    assert data.rear_window_defrost is True
    assert data.hvac_enabled is False
    assert data.hvac_mode == "cool"
    assert data.target_temperature == 18.0


def test_dict_alternate_key_variants_normalize_correctly():
    """Alternate key names (defrost/heating/climate) also normalize."""
    response = {
        "front_windshield_defrost": True,
        "rear_window_heating": True,
        "climateEnabled": True,
        "climateMode": "heat",
        "targetTemp": 25,
    }

    data = CheryData.from_api_response(response)

    assert data.front_windshield_heating is True
    assert data.rear_window_defrost is True
    assert data.hvac_enabled is True
    assert data.hvac_mode == "heat"
    assert data.target_temperature == 25.0


def test_dict_first_matching_key_wins():
    """When multiple variants are present, the first listed key takes priority."""
    response = {
        "front_windshield_heating": True,
        "frontWindshieldHeating": False,
        "front_windshield_defrost": False,
    }

    data = CheryData.from_api_response(response)

    assert data.front_windshield_heating is True


# ---------------------------------------------------------------------------
# Dict input — malformed values
# ---------------------------------------------------------------------------


def test_malformed_bool_values_normalize_to_none():
    """Non-boolean values for bool fields normalize to None."""
    response = {
        "front_windshield_heating": "not_a_bool",
        "rear_window_defrost": {"unexpected": "dict"},
        "hvac_enabled": [1, 2, 3],
    }

    data = CheryData.from_api_response(response)

    assert data.front_windshield_heating is None
    assert data.rear_window_defrost is None
    assert data.hvac_enabled is None


def test_malformed_numeric_value_normalizes_to_none():
    """Non-numeric target_temperature normalizes to None."""
    response = {
        "target_temperature": "not_a_number",
    }

    data = CheryData.from_api_response(response)

    assert data.target_temperature is None


def test_numeric_string_target_temperature_parses():
    """Numeric strings for target_temperature are coerced to float."""
    data = CheryData.from_api_response({"target_temperature": "21.5"})

    assert data.target_temperature == 21.5


def test_string_bool_representations_normalize():
    """Common string bool representations are coerced to bool."""
    data = CheryData.from_api_response(
        {
            "front_windshield_heating": "true",
            "rear_window_defrost": "off",
            "hvac_enabled": 1,
        }
    )

    assert data.front_windshield_heating is True
    assert data.rear_window_defrost is False
    assert data.hvac_enabled is True


# ---------------------------------------------------------------------------
# Dict input — missing fields
# ---------------------------------------------------------------------------


def test_missing_fields_remain_none():
    """An empty dict leaves all new fields as None."""
    data = CheryData.from_api_response({})

    assert data.front_windshield_heating is None
    assert data.rear_window_defrost is None
    assert data.hvac_enabled is None
    assert data.hvac_mode is None
    assert data.target_temperature is None


def test_none_response_returns_all_none():
    """A None response produces an empty CheryData."""
    data = CheryData.from_api_response(None)

    assert data.front_windshield_heating is None
    assert data.rear_window_defrost is None
    assert data.hvac_enabled is None
    assert data.hvac_mode is None
    assert data.target_temperature is None


def test_empty_string_values_treated_as_missing():
    """Empty-string values are treated as missing (per _first helper)."""
    data = CheryData.from_api_response(
        {
            "front_windshield_heating": "",
            "hvac_mode": "",
            "target_temperature": "",
        }
    )

    assert data.front_windshield_heating is None
    assert data.hvac_mode is None
    assert data.target_temperature is None


# ---------------------------------------------------------------------------
# VehicleStatus input
# ---------------------------------------------------------------------------


def test_vehicle_status_copies_new_fields():
    """VehicleStatus input copies the new fields through from_api_response."""
    status = VehicleStatus(
        vin="VIN456",
        front_windshield_heating=True,
        rear_window_defrost=False,
        hvac_enabled=True,
        hvac_mode="auto",
        target_temperature=21.0,
    )

    data = CheryData.from_api_response(status)

    assert data.vin == "VIN456"
    assert data.front_windshield_heating is True
    assert data.rear_window_defrost is False
    assert data.hvac_enabled is True
    assert data.hvac_mode == "auto"
    assert data.target_temperature == 21.0


def test_vehicle_status_missing_new_fields_remain_none():
    """VehicleStatus without the new fields leaves them as None."""
    status = VehicleStatus(vin="VIN789")

    data = CheryData.from_api_response(status)

    assert data.vin == "VIN789"
    assert data.front_windshield_heating is None
    assert data.rear_window_defrost is None
    assert data.hvac_enabled is None
    assert data.hvac_mode is None
    assert data.target_temperature is None


def test_vehicle_status_malformed_values_normalize_to_none():
    """Malformed values on VehicleStatus are coerced via _as_bool/_as_float."""
    status = VehicleStatus(
        vin="VIN000",
        front_windshield_heating="not_a_bool",  # type: ignore[arg-type]
        target_temperature="not_a_number",  # type: ignore[arg-type]
    )

    data = CheryData.from_api_response(status)

    assert data.front_windshield_heating is None
    assert data.target_temperature is None


# ---------------------------------------------------------------------------
# Constructor — fields are optional
# ---------------------------------------------------------------------------


def test_chery_data_constructor_does_not_require_new_fields():
    """CheryData can be constructed without any of the new fields."""
    data = CheryData(vin="VIN")

    assert data.front_windshield_heating is None
    assert data.rear_window_defrost is None
    assert data.hvac_enabled is None
    assert data.hvac_mode is None
    assert data.target_temperature is None


def test_vehicle_status_constructor_does_not_require_new_fields():
    """VehicleStatus can be constructed without any of the new fields."""
    status = VehicleStatus(vin="VIN")

    assert status.front_windshield_heating is None
    assert status.rear_window_defrost is None
    assert status.hvac_enabled is None
    assert status.hvac_mode is None
    assert status.target_temperature is None


def test_from_realtime_maps_battery_range_and_tires():
    data = CheryData.from_realtime(
        {
            "dumpEnergy": "72",
            "pureElectricRange": "60",
            "mileageSurplus": "215",
            "lFrontTyreKpa": "240",
            "rFrontTyreKpa": "242",
            "lRearTyreKpa": "238",
            "rRearTyreKpa": "241",
            "doorLock": "0",
            "chargeState": "1",
            "resultTime": "1721390000000",
        },
        vin="VIN123",
    )

    assert data.vin == "VIN123"
    assert data.battery_level == 72.0
    assert data.range_km == 275.0
    assert data.tire_pressures == {
        "front_left": 2.4,
        "front_right": 2.42,
        "rear_left": 2.38,
        "rear_right": 2.41,
    }
    assert data.is_locked is True
    assert data.is_charging is True
    assert data.last_updated == "1721390000000"


def test_merge_chery_data_keeps_base_vin_and_overlays_realtime():
    base = CheryData(vin="VIN123", battery_level=None)
    update = CheryData(vin="VIN123", battery_level=72.0, range_km=275.0)

    merged = merge_chery_data(base, update)

    assert merged.vin == "VIN123"
    assert merged.battery_level == 72.0
    assert merged.range_km == 275.0


def test_from_realtime_maps_extended_vehicle_state():
    data = CheryData.from_realtime(
        {
            "dumpEnergy": "72",
            "pureElectricRange": "103",
            "electricRange": "1600",
            "mileageSurplus": "418",
            "odometer": "4082",
            "avgHkPowerKwh50km": "18.9",
            "lFrontTyreTemp": "23.0",
            "rFrontTyreTemp": "24.0",
            "lRearTyreTemp": "22.5",
            "rRearTyreTemp": "22.0",
            "doorLock": "0",
            "chargeState": "0",
            "appointmentChargeState": "1",
            "chargeGunState": "0",
            "fastChargingGunStatus": "0",
            "engineState": "0",
            "onlineStatus": "1",
            "hVoltageState": "1",
            "frontHVACState": "1",
            "frontSetTempLeft": "22.0",
            "frontLeftDoor": "0",
            "frontRightDoor": "1",
            "backLeftDoor": "0",
            "backRightDoor": "0",
            "trunkDoor": "0",
            "frontLeftWindowState": "0",
            "frontRightWindowState": "1",
            "backLeftWindowState": "0",
            "backRightWindowState": "0",
            "steerWheelHeating": "1",
            "airPurification": "0",
            "sunroofState": "0",
            "dSeatHeatingState": "1",
            "pSeatHeatingState": "0",
            "dSeatVentilateState": "0",
            "pSeatVentilateState": "1",
            "frontWindshieldHeat": "0",
            "resultTime": "1786696731068",
        },
        vin="VIN123",
    )

    assert data.odometer_km == 4082.0
    assert data.electric_range_km == 103.0
    assert data.electric_odometer_km == 1600.0
    assert data.fuel_range_km == 418.0
    assert data.power_consumption_kwh_100km == 18.9
    assert data.hvac_enabled is True
    assert data.target_temperature == 22.0
    assert data.online is True
    assert data.hv_high_voltage_on is True
    assert data.appointment_charge is True
    assert data.steering_wheel_heating is True
    assert data.door_front_right_open is True
    assert data.window_front_right_open is True
    assert data.driver_seat_heating is True
    assert data.passenger_seat_ventilation is True
    assert data.tire_temperatures == {
        "front_left": 23.0,
        "front_right": 24.0,
        "rear_left": 22.5,
        "rear_right": 22.0,
    }


def test_apply_command_feedback_updates_lock_and_hvac():
    base = CheryData(vin="VIN123", is_locked=True, hvac_enabled=False)

    unlocked = apply_command_feedback(base, "ve_1105", action="unlock")
    climate_on = apply_command_feedback(base, "ve_1104", enabled=True)
    climate_off = apply_command_feedback(climate_on, "ve_1104", enabled=False)

    assert unlocked.is_locked is False
    assert climate_on.hvac_enabled is True
    assert climate_off.hvac_enabled is False


def test_vehicle_display_name_prefers_nickname():
    data = CheryData(
        vehicle_nickname="Tiggo 9",
        vehicle_full_name="Tiggo 9 PHEV",
    )

    assert vehicle_display_name(data) == "Tiggo 9"


def test_from_api_response_maps_vehicle_list_metadata():
    data = CheryData.from_api_response(
        {
            "vin": "VIN123",
            "fullName": "Tiggo 9 PHEV",
            "colorNameEn": "EXEED White",
            "carPicture": "https://example.com/car.png",
            "nickname": "Tiggo 9",
            "minTemperature": 16.0,
            "maxTemperature": 30.0,
        }
    )

    assert data.vin == "VIN123"
    assert data.vehicle_full_name == "Tiggo 9 PHEV"
    assert data.vehicle_color_name_en == "EXEED White"
    assert data.vehicle_picture_url == "https://example.com/car.png"
    assert data.vehicle_nickname == "Tiggo 9"
    assert data.min_temperature == 16.0
    assert data.max_temperature == 30.0


def test_from_realtime_maps_average_fuel_consumption():
    data = CheryData.from_realtime({"averageFuel": "7.5"}, vin="VIN123")

    assert data.average_fuel_consumption == 7.5


def test_from_realtime_maps_charge_appoint_plan():
    data = CheryData.from_realtime(
        {
            "chargeAppointPlans": [
                {
                    "cycleData": [1, 2, 3, 4, 5, 6, 7],
                    "startTime": 465,
                    "switchStatus": "1",
                    "timeConsuming": 360,
                }
            ]
        },
        vin="VIN123",
    )

    assert data.scheduled_charge_enabled is True
    assert data.charge_appoint_plan is not None
    assert data.charge_appoint_plan["startTime"] == 465


def test_apply_command_feedback_updates_scheduled_charging():
    base = CheryData(vin="VIN123")

    updated = apply_command_feedback(
        base,
        "ve_1202",
        enabled=True,
        start_minutes=480,
        duration_hours=6,
    )

    assert updated.scheduled_charge_enabled is True
    assert updated.charge_appoint_plan is not None
    assert updated.charge_appoint_plan["startTime"] == 480
    assert updated.charge_appoint_plan["timeConsuming"] == 360


def test_from_realtime_maps_charge_status_and_remaining_time():
    data = CheryData.from_realtime(
        {
            "chargeState": "1",
            "appointmentChargeState": "2",
            "remainChargeTime": "42",
            "lSeatHeatingState2": "1",
        },
        vin="VIN123",
    )

    assert data.charge_status == "charging"
    assert data.appointment_charge_status == "running"
    assert data.remain_charge_time_min == 42.0
    assert data.rear_left_seat_heating is True


def test_apply_command_feedback_updates_covers_and_seats():
    base = CheryData(vin="VIN123")
    opened = apply_command_feedback(base, "ve_1205", action="open")
    heated = apply_command_feedback(
        base, "ve_1204", enabled=True, seat_field="mSeatHeating"
    )

    assert opened.trunk_open is True
    assert heated.driver_seat_heating is True
    assert heated.driver_seat_ventilation is False
