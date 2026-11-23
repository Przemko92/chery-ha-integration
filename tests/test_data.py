# pyright: reportArgumentType=false, reportOptionalSubscript=false

"""Tests for CheryData.from_api_response normalization of HVAC/lock feedback fields."""

import inspect
from datetime import UTC, datetime

import pytest

pytest.importorskip("homeassistant")

from homeassistant.helpers.device_registry import DeviceRegistry

from custom_components.chery_europe.const import DOMAIN
from custom_components.chery_europe.data import (
    CheryData,
    apply_charge_appointment,
    apply_command_feedback,
    apply_data_freshness,
    apply_location,
    merge_chery_data,
    parse_charge_appointment,
    parse_theft_alarm,
    vehicle_choices,
    vehicle_display_name,
)
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
    assert data.last_updated == "2024-07-19T11:53:20+00:00"


def test_from_realtime_maps_charging_power_and_traction_battery():
    data = CheryData.from_realtime(
        {
            "chargingPower": "6.6",
            "totalVoltage": "323.1",
            "totalCurrent": "-12.5",
        },
        vin="VIN123",
    )

    assert data.charging_power_kw == 6.6
    assert data.battery_voltage_v == 323.1
    assert data.battery_current_a == -12.5


def test_from_realtime_derives_charging_power_when_phev_omits_the_field():
    """PHEV realtime omits chargingPower; pack power is |V × I| while charging."""
    charging = CheryData.from_realtime(
        {"chargeState": "1", "totalVoltage": "400", "totalCurrent": "-16.5"},
        vin="VIN123",
    )
    charging_float_code = CheryData.from_realtime(
        {"chargeState": "1.0", "totalVoltage": "323.1", "totalCurrent": "20.4"},
        vin="VIN123",
    )
    idle = CheryData.from_realtime(
        {"chargeState": "0", "totalVoltage": "350", "totalCurrent": "12"},
        vin="VIN123",
    )
    missing = CheryData.from_realtime(
        {"totalVoltage": "350", "totalCurrent": "12"},
        vin="VIN123",
    )
    hv_off = CheryData.from_realtime(
        {"chargeState": "1", "totalVoltage": "0", "totalCurrent": "-1000"},
        vin="VIN123",
    )

    assert charging.charging_power_kw == 6.6
    assert charging_float_code.charging_power_kw == 6.59
    assert idle.charging_power_kw == 0.0
    assert missing.charging_power_kw is None
    assert hv_off.charging_power_kw is None


def test_reported_charging_power_wins_over_pack_power():
    data = CheryData.from_realtime(
        {
            "chargingPower": "7.2",
            "chargeState": "1",
            "totalVoltage": "400",
            "totalCurrent": "-10",
        },
        vin="VIN123",
    )

    assert data.charging_power_kw == 7.2


def test_from_realtime_ignores_hv_off_voltage_and_current_placeholders():
    """0 V and -1000 A mean the high-voltage system is off, not a live reading."""
    data = CheryData.from_realtime(
        {"totalVoltage": "0", "totalCurrent": "-1000", "chargingPower": "0"},
        vin="VIN123",
    )

    assert data.battery_voltage_v is None
    assert data.battery_current_a is None
    assert data.charging_power_kw == 0.0


def test_from_realtime_maps_front_windshield_defrost():
    data = CheryData.from_realtime(
        {"frontWindshieldHeat": "0", "fWinHeatingState": "1"}, vin="VIN123"
    )
    assert data.front_windshield_heating is False
    assert data.front_windshield_defrost is True


def test_from_realtime_maps_vehicle_speed():
    data = CheryData.from_realtime({"vehicleSpeed": "38"}, vin="VIN123")

    assert data.gps_speed == 38.0


def test_apply_location_keeps_vehicle_timestamp():
    """GPS resultTime is the fix age and must not replace the status clock."""
    data = CheryData(
        vin="VIN123",
        battery_level=80,
        last_updated="2026-11-17T10:09:00+00:00",
    )
    updated = apply_location(
        data,
        {
            "lat": "50.06",
            "lon": "19.93",
            "resultTime": "1763316900000",
            "gpsTime": "1763316900000",
        },
    )

    assert updated.last_updated == "2026-11-17T10:09:00+00:00"
    assert updated.gps_time is not None
    assert updated.latitude == pytest.approx(50.06)


def test_freshness_stays_on_newer_timestamp_when_telemetry_is_unchanged():
    previous = CheryData(
        vin="VIN123",
        battery_level=80,
        odometer_km=4082,
        last_updated="2026-11-17T10:09:00+00:00",
    )
    polled = replace_same_telemetry(previous, "2026-11-16T18:15:00+00:00")

    assert apply_data_freshness(previous, polled).last_updated == previous.last_updated


def test_freshness_advances_when_telemetry_changes_and_never_backwards():
    previous = CheryData(
        vin="VIN123",
        battery_level=80,
        last_updated="2026-11-17T10:09:00+00:00",
    )
    changed = CheryData(
        vin="VIN123",
        battery_level=79,
        last_updated="2026-11-16T18:15:00+00:00",
    )
    before = datetime.now(UTC)
    updated = apply_data_freshness(previous, changed)
    after = datetime.now(UTC)

    stamped = datetime.fromisoformat(updated.last_updated)
    assert before <= stamped <= after
    assert stamped > datetime.fromisoformat(previous.last_updated)


def test_freshness_keeps_car_timestamp_on_the_first_frame():
    first = CheryData(vin="VIN123", battery_level=80, last_updated="2026-11-17T10:09:00+00:00")

    assert apply_data_freshness(None, first).last_updated == first.last_updated


def replace_same_telemetry(data: CheryData, last_updated: str) -> CheryData:
    return CheryData(
        vin=data.vin,
        battery_level=data.battery_level,
        odometer_km=data.odometer_km,
        latitude=50.0,
        longitude=19.9,
        gps_time=last_updated,
        last_updated=last_updated,
    )


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
    assert data.window_front_right_position == 50
    assert data.window_front_left_position == 0
    assert data.sunroof_position == 0
    assert data.driver_seat_heating is True
    assert data.passenger_seat_ventilation is True
    assert data.tire_temperatures == {
        "front_left": 23.0,
        "front_right": 24.0,
        "rear_left": 22.5,
        "rear_right": 22.0,
    }
    assert data.last_updated == "2026-08-14T08:38:51.068000+00:00"


def test_from_realtime_maps_window_and_sunroof_vent_state():
    data = CheryData.from_realtime(
        {
            "frontLeftWindowState": "1",
            "frontRightWindowState": "0",
            "backLeftWindowState": "3",
            "backRightWindowState": "0",
            "sunroofState": "2",
        },
        vin="VIN123",
    )

    assert data.window_front_left_open is True
    assert data.window_front_left_position == 50
    assert data.window_front_right_position == 0
    assert data.window_rear_left_position == 100
    assert data.sunroof_open is True
    assert data.sunroof_position == 50


def test_from_realtime_maps_sunroof_open_state():
    data = CheryData.from_realtime({"sunroofState": "3"}, vin="VIN123")

    assert data.sunroof_open is True
    assert data.sunroof_position == 100


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


def test_vehicle_display_name_never_returns_the_vin():
    data = CheryData(vin="LVVDB21B0PD123456", vehicle_nickname="LVVDB21B0PD123456")

    assert vehicle_display_name(data) == "Chery Vehicle"
    assert "LVVDB21B0PD123456" not in vehicle_display_name(data)


def test_scoped_device_lookup_matches_ha_signature():
    """The scoped registry call must match what HA declares, not what we assume.

    ``async_get_device_by_identifier`` takes the full ``(domain, identifier)``
    tuple plus the entry id; a mock registry happily accepts any shape, so bind
    the real signature here instead.
    """
    sig = inspect.signature(DeviceRegistry.async_get_device_by_identifier)
    sig.bind(None, (DOMAIN, "vin"), "entry-1")


def test_entity_id_renames_match_the_polish_names() -> None:
    """Every rename target must be what the Polish name actually slugifies to."""
    import json
    from pathlib import Path

    from homeassistant.util import slugify

    from custom_components.chery_europe.entity import ENTITY_ID_RENAMES, UID_TRANSLATION_KEYS

    path = Path(__file__).parent.parent / "custom_components/chery_europe/translations/pl.json"
    translations = json.loads(path.read_text(encoding="utf-8"))["entity"]
    for domain, key, _old_slug, new_slug in ENTITY_ID_RENAMES:
        translation_key = UID_TRANSLATION_KEYS.get(key, key)
        entry = translations.get(domain, {}).get(translation_key)
        assert entry is not None and "name" in entry, (
            f"{domain}.{translation_key} has no Polish name"
        )
        assert entry["name"] != "", f"{domain}.{translation_key} has an empty Polish name"
        assert slugify(entry["name"]) == new_slug, (
            domain,
            translation_key,
            entry["name"],
            new_slug,
        )


def test_tire_entity_ids_group_by_wheel() -> None:
    """Pressure and temperature of one wheel must end up next to each other."""
    from types import SimpleNamespace
    from unittest.mock import Mock, patch

    from custom_components.chery_europe.entity import async_rename_entity_ids

    entity = SimpleNamespace(
        entity_id="sensor.wspolne_tiggo_cisnienie_przedniej_lewej_opony",
        unique_id="wspolne_tiggo_tire_pressure_front_left",
        domain="sensor",
    )
    registry = Mock()
    registry.async_get.return_value = None
    hass = Mock()
    entry = SimpleNamespace(entry_id="entry-1")

    with (
        patch("custom_components.chery_europe.entity.er.async_get", return_value=registry),
        patch(
            "custom_components.chery_europe.entity.er.async_entries_for_config_entry",
            return_value=[entity],
        ),
    ):
        async_rename_entity_ids(hass, entry)

    registry.async_update_entity.assert_called_once_with(
        "sensor.wspolne_tiggo_cisnienie_przedniej_lewej_opony",
        new_entity_id="sensor.wspolne_tiggo_kolo_przednie_lewe_cisnienie",
    )


def test_alarm_content_entity_id_follows_the_new_translation() -> None:
    """A renamed translation must move the stale entity id, not leave it behind."""
    from types import SimpleNamespace
    from unittest.mock import Mock, call, patch

    from custom_components.chery_europe.entity import async_rename_entity_ids

    entities = [
        SimpleNamespace(
            entity_id="sensor.wspolne_tiggo_tresc_alarmow",
            unique_id="wspolne_tiggo_alerts_content",
            domain="sensor",
        ),
        SimpleNamespace(
            entity_id="sensor.wspolne_tiggo_nieprzeczytane_wiadomosci",
            unique_id="wspolne_tiggo_messages_unread",
            domain="sensor",
        ),
    ]
    registry = Mock()
    registry.async_get.return_value = None
    hass = Mock()
    entry = SimpleNamespace(entry_id="entry-1")

    with (
        patch("custom_components.chery_europe.entity.er.async_get", return_value=registry),
        patch(
            "custom_components.chery_europe.entity.er.async_entries_for_config_entry",
            return_value=entities,
        ),
    ):
        async_rename_entity_ids(hass, entry)

    assert registry.async_update_entity.call_args_list == [
        call(
            "sensor.wspolne_tiggo_tresc_alarmow",
            new_entity_id="sensor.wspolne_tiggo_alarmy_tresc",
        ),
        call(
            "sensor.wspolne_tiggo_nieprzeczytane_wiadomosci",
            new_entity_id="sensor.wspolne_tiggo_wiadomosci_nieprzeczytane",
        ),
    ]


def test_registry_names_lose_the_vin():
    from types import SimpleNamespace
    from unittest.mock import Mock, patch

    from custom_components.chery_europe.const import DOMAIN
    from custom_components.chery_europe.entity import async_drop_vin_from_names

    vin = "LVVDB21B0PD123456"
    entity = SimpleNamespace(
        entity_id=f"sensor.{vin.lower()}_battery_level",
        unique_id=f"{vin}_battery_level",
        name=vin,
        original_name="Battery",
    )
    device = SimpleNamespace(
        id="dev1",
        identifiers={(DOMAIN, vin)},
        name=vin,
        # Older builds blanked the serial number; the migration restores the VIN.
        serial_number=None,
    )
    entity_reg = Mock()
    entity_reg.async_generate_entity_id.return_value = "sensor.battery_level"
    device_reg = Mock()
    device_reg.async_get_device.return_value = device
    # The scoped lookup is the current API; the deprecated one is only a fallback.
    device_reg.async_get_device_by_identifier.return_value = device
    hass = Mock()
    entry = SimpleNamespace(
        entry_id="entry-1",
        title=vin,
        runtime_data=SimpleNamespace(
            data=CheryData(vin=vin, vehicle_nickname="Tiggo 8")
        ),
    )

    with (
        patch(
            "custom_components.chery_europe.entity.er.async_get",
            return_value=entity_reg,
        ),
        patch(
            "custom_components.chery_europe.entity.er.async_entries_for_config_entry",
            return_value=[entity],
        ),
        patch(
            "custom_components.chery_europe.entity.dr.async_get",
            return_value=device_reg,
        ),
    ):
        async_drop_vin_from_names(hass, entry, vin)

    device_reg.async_get_device_by_identifier.assert_called_once_with(
        (DOMAIN, vin), "entry-1"
    )
    device_reg.async_get_device.assert_not_called()
    device_update = device_reg.async_update_device.call_args.kwargs
    assert (DOMAIN, "entry-1") in device_update["new_identifiers"]
    assert (DOMAIN, vin) not in device_update["new_identifiers"]
    assert device_update["name"] == "Tiggo 8"
    assert device_update["serial_number"] == vin
    entity_update = entity_reg.async_update_entity.call_args.kwargs
    assert entity_update["new_unique_id"] == "entry-1_battery_level"
    assert entity_update["new_entity_id"] == "sensor.battery_level"
    assert entity_update["name"] is None
    assert vin not in str(entity_update)


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


def test_apply_command_feedback_front_defrost_rides_on_climate():
    base = CheryData(vin="VIN123", hvac_enabled=False)

    on = apply_command_feedback(base, "ve_1108", enabled=True)
    off = apply_command_feedback(on, "ve_1108", enabled=False)

    assert on.front_windshield_defrost is True
    assert on.hvac_enabled is True
    assert off.front_windshield_defrost is False
    assert off.hvac_enabled is False


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


def test_remaining_charge_time_clears_when_charging_stops():
    finished = CheryData.from_realtime(
        {"chargeState": "2", "remainChargeTime": "4"},
        vin="VIN123",
    )
    idle = CheryData.from_realtime({"chargeState": "0"}, vin="VIN123")
    still_charging = CheryData.from_realtime(
        {"chargeState": "1", "remainChargeTime": "4"},
        vin="VIN123",
    )
    explicit_zero = CheryData.from_realtime(
        {"chargeState": "1", "remainChargeTime": "0"},
        vin="VIN123",
    )
    merged = merge_chery_data(
        CheryData(vin="VIN123", remain_charge_time_min=4.0),
        finished,
    )

    assert finished.remain_charge_time_min == 0.0
    assert idle.remain_charge_time_min == 0.0
    assert still_charging.remain_charge_time_min == 4.0
    assert explicit_zero.remain_charge_time_min == 0.0
    assert merged.remain_charge_time_min == 0.0


def test_apply_command_feedback_updates_covers_and_seats():
    base = CheryData(vin="VIN123")
    opened = apply_command_feedback(base, "ve_1205", action="open")
    heated = apply_command_feedback(
        base, "ve_1204", enabled=True, seat_field="mSeatHeating"
    )
    vented_windows = apply_command_feedback(base, "ve_1206", action="vent")
    tilted_sunroof = apply_command_feedback(base, "ve_1207", action="tilt")
    closed_sunroof = apply_command_feedback(base, "ve_1207", action="close")

    assert opened.trunk_open is True
    assert heated.driver_seat_heating is True
    assert heated.driver_seat_ventilation is False
    assert vented_windows.window_front_left_open is True
    assert vented_windows.window_front_left_position == 50
    assert vented_windows.window_rear_right_position == 50
    assert tilted_sunroof.sunroof_open is True
    assert tilted_sunroof.sunroof_position == 50
    assert closed_sunroof.sunroof_open is False
    assert closed_sunroof.sunroof_position == 0


def test_parse_charge_appointment_reads_main_switch_and_plan():
    enabled, plan = parse_charge_appointment(
        {
            "code": "000000",
            "data": {
                "mainSwitch": 1,
                "chargeAppointPlans": [
                    {
                        "startTime": 1320,
                        "timeConsuming": 480,
                        "switchStatus": 1,
                        "cycleData": [1, 2, 3, 4, 5, 6, 7],
                    }
                ],
            },
        }
    )

    assert enabled is True
    assert plan["startTime"] == 1320
    assert plan["timeConsuming"] == 480


def test_parse_charge_appointment_accepts_string_plan_and_off_switch():
    enabled, plan = parse_charge_appointment(
        {
            "data": {
                "mainSwitch": 0,
                "chargeAppointPlans": (
                    "[{'startTime': 480, 'timeConsuming': 360, 'switchStatus': '0'}]"
                ),
            }
        }
    )

    assert enabled is False
    assert plan["startTime"] == 480


def test_parse_charge_appointment_ignores_empty_payload():
    assert parse_charge_appointment({"code": "000000", "data": {}}) is None
    assert parse_charge_appointment(None) is None


def test_apply_charge_appointment_keeps_plan_when_query_failed():
    current = CheryData(
        vin="VIN123",
        scheduled_charge_enabled=True,
        charge_appoint_plan={"startTime": 480, "timeConsuming": 360},
    )

    assert apply_charge_appointment(current, None) is current


def test_apply_command_feedback_air_purification():
    base = CheryData(vin="VIN123", hvac_enabled=False)
    on = apply_command_feedback(base, "ve_1109", enabled=True)
    off = apply_command_feedback(on, "ve_1109", enabled=False)

    assert on.air_purification is True
    assert on.hvac_enabled is True
    assert off.air_purification is False
    assert off.hvac_enabled is True


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", False),
        ("1", True),
        ("2", True),
        ("3", True),
        (3, True),
        ("", None),
        (None, None),
    ],
)
def test_from_realtime_seat_states_are_levels(raw, expected):
    """Seat heating/ventilation report a level; any level above 0 is on."""
    fields = {
        "dSeatHeatingState": "driver_seat_heating",
        "pSeatHeatingState": "passenger_seat_heating",
        "dSeatVentilateState": "driver_seat_ventilation",
        "pSeatVentilateState": "passenger_seat_ventilation",
        "lSeatHeatingState2": "rear_left_seat_heating",
        "rSeatHeatingState2": "rear_right_seat_heating",
        "lSeatVentilateState2": "rear_left_seat_ventilation",
        "rSeatVentilateState2": "rear_right_seat_ventilation",
    }
    data = CheryData.from_realtime({key: raw for key in fields}, vin="VIN123")

    for attr in fields.values():
        assert getattr(data, attr) is expected, attr


def test_from_realtime_keeps_seat_levels():
    data = CheryData.from_realtime(
        {
            "dSeatHeatingState": "2",
            "pSeatVentilateState": "0",
            "lSeatHeatingState2": "3",
        },
        vin="VIN123",
    )

    assert data.seat_levels == {
        "driver_seat_heating": 2,
        "passenger_seat_ventilation": 0,
        "rear_left_seat_heating": 3,
    }


def test_apply_command_feedback_seat_level():
    base = CheryData(vin="VIN123", seat_levels={"driver_seat_heating": 0})
    on = apply_command_feedback(
        base, "ve_1204", enabled=True, seat_field="mSeatHeating", level=1
    )
    off = apply_command_feedback(
        on, "ve_1204", enabled=False, seat_field="mSeatHeating"
    )

    assert on.driver_seat_heating is True
    assert on.seat_levels["driver_seat_heating"] == 1
    assert off.seat_levels["driver_seat_heating"] == 0


def test_heat_everything_feedback_turns_the_cabin_on():
    base = CheryData(vin="VIN123", cool_everything=True, hvac_enabled=False)
    heated = apply_command_feedback(base, "ve_1301", enabled=True)
    assert heated.heat_everything is True
    assert heated.cool_everything is False
    assert heated.hvac_enabled is True
    assert heated.front_windshield_heating is True
    assert heated.driver_seat_heating is True
    assert heated.seat_levels["driver_seat_heating"] == 3
    assert heated.driver_seat_ventilation is False


def test_parse_theft_alarm_reads_nested_switch():
    assert parse_theft_alarm({"body": {"theftAlarmSwitch": "1"}}) is True
    assert parse_theft_alarm({"data": {"theftAlarmSwitch": "0"}}) is False
    assert parse_theft_alarm({"code": "000000"}) is None


def test_vehicle_choices_hide_the_full_vin_and_split_duplicate_labels():
    choices = vehicle_choices(
        [
            {"vin": "LVVDB21B0PD111111", "nickname": "Tiggo", "fullName": "Tiggo 9"},
            {"vin": "LVVDB21B0PD222222", "nickname": "Tiggo", "fullName": "Tiggo 9"},
        ]
    )
    assert choices[0][0] == "LVVDB21B0PD111111"
    assert "LVVDB21B0PD111111" not in choices[0][1]
    assert choices[0][1].endswith("(1111)")
    assert choices[1][1].endswith("(2222)")


def test_parse_charge_appointment_unwraps_the_tspconsole_body():
    """chargeAppointQuery answers {"code", "body"}, not {"data"}."""
    enabled, plan = parse_charge_appointment(
        {
            "code": "000000",
            "sign": "1TGBQ9PVC5JUTI5Z6MCEM0PLYBQ2DN/QQQ7+PSJELMI=",
            "body": {
                "mainSwitch": 0,
                "vin": "LVVDB21B0PD000042",
                "id": 50056,
                "chargeAppointPlans": [
                    {
                        "timeConsuming": 780,
                        "chargeAppointMainId": 50056,
                        "cycleData": [1, 2, 3, 4, 5, 6, 7],
                        "startTime": 375,
                        "id": 421517421,
                        "switchStatus": 0,
                    }
                ],
            },
        }
    )

    assert enabled is False
    assert plan is not None
    assert plan["startTime"] == 375
    assert plan["timeConsuming"] == 780
    from custom_components.chery_europe.charge_schedule import plan_duration_hours

    assert plan_duration_hours(plan) == 13
