from __future__ import annotations

import ast
from dataclasses import dataclass, replace
from typing import Any

from .types.vehicle_models import VehicleStatus
from .vehicle_commands import build_charge_plan


@dataclass(frozen=True)
class CheryData:
    """Normalized vehicle data from Chery Europe."""

    vin: str | None = None
    battery_level: float | None = None
    fuel_level: float | None = None
    range_km: float | None = None
    electric_range_km: float | None = None
    electric_odometer_km: float | None = None
    fuel_range_km: float | None = None
    odometer_km: float | None = None
    power_consumption_kwh_100km: float | None = None
    average_fuel_consumption: float | None = None
    vehicle_full_name: str | None = None
    vehicle_color_name_en: str | None = None
    vehicle_picture_url: str | None = None
    vehicle_nickname: str | None = None
    min_temperature: float | None = None
    max_temperature: float | None = None
    tire_pressures: dict[str, float | None] | None = None
    tire_temperatures: dict[str, float | None] | None = None
    interior_temperature: float | None = None
    exterior_temperature: float | None = None
    is_locked: bool | None = None
    is_charging: bool | None = None
    appointment_charge: bool | None = None
    scheduled_charge_enabled: bool | None = None
    charge_appoint_plan: dict[str, Any] | None = None
    charge_gun_connected: bool | None = None
    fast_charge_gun_connected: bool | None = None
    engine_on: bool | None = None
    online: bool | None = None
    hv_high_voltage_on: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    last_updated: str | None = None
    front_windshield_heating: bool | None = None
    rear_window_defrost: bool | None = None
    steering_wheel_heating: bool | None = None
    air_purification: bool | None = None
    sunroof_open: bool | None = None
    hvac_enabled: bool | None = None
    hvac_mode: str | None = None
    target_temperature: float | None = None
    door_front_left_open: bool | None = None
    door_front_right_open: bool | None = None
    door_rear_left_open: bool | None = None
    door_rear_right_open: bool | None = None
    trunk_open: bool | None = None
    window_front_left_open: bool | None = None
    window_front_right_open: bool | None = None
    window_rear_left_open: bool | None = None
    window_rear_right_open: bool | None = None
    driver_seat_heating: bool | None = None
    passenger_seat_heating: bool | None = None
    driver_seat_ventilation: bool | None = None
    passenger_seat_ventilation: bool | None = None

    @classmethod
    def from_api_response(cls, response: dict[str, Any] | VehicleStatus | None) -> CheryData:
        """Build normalized data from an API response without requiring all fields."""
        if response is None:
            return cls()

        try:
            if isinstance(response, VehicleStatus):
                return cls(
                    vin=response.vin,
                    battery_level=_as_float(response.battery_level),
                    fuel_level=_as_float(response.fuel_level),
                    range_km=_as_float(response.range_km),
                    tire_pressures=_normalize_tire_pressures(response.tire_pressures),
                    interior_temperature=_as_float(response.interior_temperature),
                    exterior_temperature=_as_float(response.exterior_temperature),
                    is_locked=_as_bool(response.is_locked),
                    is_charging=_as_bool(response.is_charging),
                    latitude=_as_float(response.latitude),
                    longitude=_as_float(response.longitude),
                    last_updated=response.last_updated,
                    front_windshield_heating=_as_bool(response.front_windshield_heating),
                    rear_window_defrost=_as_bool(response.rear_window_defrost),
                    hvac_enabled=_as_bool(response.hvac_enabled),
                    hvac_mode=response.hvac_mode,
                    target_temperature=_as_float(response.target_temperature),
                    vehicle_full_name=response.vehicle_full_name,
                    vehicle_color_name_en=response.vehicle_color_name_en,
                    vehicle_picture_url=response.vehicle_picture_url,
                    vehicle_nickname=response.vehicle_nickname,
                    min_temperature=_as_float(response.min_temperature),
                    max_temperature=_as_float(response.max_temperature),
                )

            if not isinstance(response, dict):
                return cls()

            return cls(
                vin=_first(response, "vin", "VIN", "vehicleVin"),
                battery_level=_as_float(_first(response, "battery_level", "batteryLevel", "soc")),
                fuel_level=_as_float(_first(response, "fuel_level", "fuelLevel")),
                range_km=_as_float(_first(response, "range_km", "rangeKm", "range", "drivingRange")),
                tire_pressures=_normalize_tire_pressures(
                    _first(response, "tire_pressures", "tirePressures", "tpms")
                ),
                interior_temperature=_as_float(
                    _first(response, "interior_temperature", "interiorTemperature", "insideTemperature")
                ),
                exterior_temperature=_as_float(
                    _first(response, "exterior_temperature", "exteriorTemperature", "outsideTemperature")
                ),
                is_locked=_as_bool(_first(response, "is_locked", "isLocked", "locked")),
                is_charging=_as_bool(_first(response, "is_charging", "isCharging", "charging")),
                latitude=_as_float(_first(response, "latitude", "lat")),
                longitude=_as_float(_first(response, "longitude", "lon", "lng")),
                last_updated=_first(response, "last_updated", "lastUpdated", "timestamp", "updateTime"),
                front_windshield_heating=_as_bool(
                    _first(
                        response,
                        "front_windshield_heating",
                        "frontWindshieldHeating",
                        "front_windshield_defrost",
                    )
                ),
                rear_window_defrost=_as_bool(
                    _first(
                        response,
                        "rear_window_defrost",
                        "rearWindowDefrost",
                        "rear_window_heating",
                    )
                ),
                hvac_enabled=_as_bool(
                    _first(response, "hvac_enabled", "hvacEnabled", "climateEnabled")
                ),
                hvac_mode=_first(response, "hvac_mode", "hvacMode", "climateMode"),
                target_temperature=_as_float(
                    _first(response, "target_temperature", "targetTemperature", "targetTemp")
                ),
                vehicle_full_name=_first(response, "vehicle_full_name", "fullName"),
                vehicle_color_name_en=_first(
                    response, "vehicle_color_name_en", "colorNameEn", "colorName"
                ),
                vehicle_picture_url=_first(response, "vehicle_picture_url", "carPicture"),
                vehicle_nickname=_first(response, "vehicle_nickname", "nickname"),
                min_temperature=_as_float(_first(response, "min_temperature", "minTemperature")),
                max_temperature=_as_float(_first(response, "max_temperature", "maxTemperature")),
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            return cls()

    @classmethod
    def from_realtime(
        cls,
        payload: dict[str, Any],
        vin: str | None = None,
    ) -> CheryData:
        """Build normalized data from a tspconsole realtime payload."""
        battery_level = _as_float(payload.get("dumpEnergy"))
        electric_range = _as_float(
            _first(payload, "pureElectricRange", "dynamicPureElectricRange")
        )
        fuel_range = _as_float(payload.get("mileageSurplus"))
        range_km = None
        if electric_range is not None or fuel_range is not None:
            range_km = (electric_range or 0.0) + (fuel_range or 0.0)

        tire_pressures = {
            "front_left": _tire_pressure_bar(payload, "lFrontTyreKpa", "lFrontTyre"),
            "front_right": _tire_pressure_bar(payload, "rFrontTyreKpa", "rFrontTyre"),
            "rear_left": _tire_pressure_bar(payload, "lRearTyreKpa", "lRearTyre"),
            "rear_right": _tire_pressure_bar(payload, "rRearTyreKpa", "rRearTyre"),
        }
        if not any(value is not None for value in tire_pressures.values()):
            tire_pressures = None

        door_lock = payload.get("doorLock")
        is_locked = None
        if door_lock is not None:
            is_locked = str(door_lock) == "0"

        charge_state = payload.get("chargeState")
        is_charging = None
        if charge_state is not None:
            is_charging = str(charge_state) == "1"

        charge_plan = _parse_charge_appoint_plan(payload.get("chargeAppointPlans"))
        scheduled_charge_enabled = _plan_switch_on(charge_plan)

        hvac_enabled = None
        front_hvac = payload.get("frontHVACState")
        if front_hvac is not None:
            hvac_enabled = str(front_hvac) not in {"0", ""}

        tire_temperatures = {
            "front_left": _as_float(payload.get("lFrontTyreTemp")),
            "front_right": _as_float(payload.get("rFrontTyreTemp")),
            "rear_left": _as_float(payload.get("lRearTyreTemp")),
            "rear_right": _as_float(payload.get("rRearTyreTemp")),
        }
        if not any(value is not None for value in tire_temperatures.values()):
            tire_temperatures = None

        electric_range_km = _as_float(
            _first(payload, "pureElectricRange", "dynamicPureElectricRange")
        )
        fuel_range_km = _as_float(payload.get("mileageSurplus"))

        return cls(
            vin=vin,
            battery_level=battery_level,
            fuel_level=_as_float(payload.get("oilSurplus")),
            range_km=range_km,
            electric_range_km=electric_range_km,
            electric_odometer_km=_as_float(payload.get("electricRange")),
            fuel_range_km=fuel_range_km,
            odometer_km=_as_float(_first(payload, "odometer", "odometerMile")),
            power_consumption_kwh_100km=_as_float(
                _first(payload, "avgHkPowerKwh50km", "avgHkPowerWhkm")
            ),
            average_fuel_consumption=_as_float(payload.get("averageFuel")),
            tire_pressures=tire_pressures,
            tire_temperatures=tire_temperatures,
            interior_temperature=_as_float(
                _first(payload, "inCarTemperature", "insideTemperature")
            ),
            exterior_temperature=_as_float(
                _first(payload, "outsideTemperature", "outCarTemperature")
            ),
            is_locked=is_locked,
            is_charging=is_charging,
            appointment_charge=_state_on(payload.get("appointmentChargeState")),
            scheduled_charge_enabled=scheduled_charge_enabled,
            charge_appoint_plan=charge_plan,
            charge_gun_connected=_state_on(payload.get("chargeGunState")),
            fast_charge_gun_connected=_state_on(payload.get("fastChargingGunStatus")),
            engine_on=_state_on(payload.get("engineState")),
            online=_state_on(payload.get("onlineStatus")),
            hv_high_voltage_on=_state_on(payload.get("hVoltageState")),
            latitude=_as_float(_first(payload, "lat", "latitude")),
            longitude=_as_float(_first(payload, "lon", "longitude", "lng")),
            last_updated=_first(payload, "resultTime", "lastUpdated", "timestamp"),
            front_windshield_heating=_state_on(
                _first(payload, "frontWindshieldHeat", "fWinHeatingState", "frontWindHeatState")
            ),
            rear_window_defrost=_state_on(
                _first(payload, "backDefrostingState", "backDefrosting")
            ),
            steering_wheel_heating=_state_on(payload.get("steerWheelHeating")),
            air_purification=_state_on(payload.get("airPurification")),
            sunroof_open=_is_open(payload.get("sunroofState")),
            hvac_enabled=hvac_enabled,
            target_temperature=_as_float(
                _first(payload, "frontSetTempLeft", "frontSetTempRight", "targetTemp")
            ),
            door_front_left_open=_is_open(payload.get("frontLeftDoor")),
            door_front_right_open=_is_open(payload.get("frontRightDoor")),
            door_rear_left_open=_is_open(payload.get("backLeftDoor")),
            door_rear_right_open=_is_open(payload.get("backRightDoor")),
            trunk_open=_is_open(payload.get("trunkDoor")),
            window_front_left_open=_is_open(payload.get("frontLeftWindowState")),
            window_front_right_open=_is_open(payload.get("frontRightWindowState")),
            window_rear_left_open=_is_open(payload.get("backLeftWindowState")),
            window_rear_right_open=_is_open(payload.get("backRightWindowState")),
            driver_seat_heating=_state_on(payload.get("dSeatHeatingState")),
            passenger_seat_heating=_state_on(payload.get("pSeatHeatingState")),
            driver_seat_ventilation=_state_on(payload.get("dSeatVentilateState")),
            passenger_seat_ventilation=_state_on(payload.get("pSeatVentilateState")),
        )


def vehicle_display_name(data: CheryData) -> str:
    """Return the user-facing vehicle label."""
    return data.vehicle_nickname or data.vehicle_full_name or "Chery Vehicle"


def merge_chery_data(base: CheryData, update: CheryData) -> CheryData:
    """Merge realtime values into a base vehicle record."""
    merged = base
    for field_name in CheryData.__dataclass_fields__:
        value = getattr(update, field_name)
        if value is not None:
            merged = replace(merged, **{field_name: value})
    return merged


def apply_command_feedback(data: CheryData, command_id: str, **kwargs: Any) -> CheryData:
    """Optimistically update coordinator data after a successful remote command."""
    if command_id == "ve_1104":
        enabled = kwargs.get("enabled")
        if enabled is True:
            return replace(data, hvac_enabled=True)
        if enabled is False:
            return replace(data, hvac_enabled=False)
    if command_id == "ve_1105":
        action = str(kwargs.get("action", "lock")).lower()
        return replace(data, is_locked=action != "unlock")
    if command_id == "ve_1103":
        enabled = kwargs.get("enabled")
        if enabled is not None:
            return replace(data, front_windshield_heating=enabled)
    if command_id == "ve_1135":
        enabled = kwargs.get("enabled")
        if enabled is not None:
            return replace(data, rear_window_defrost=enabled)
    if command_id == "ve_1201":
        enabled = kwargs.get("enabled")
        if enabled is True:
            return replace(data, is_charging=True)
        if enabled is False:
            return replace(data, is_charging=False)
    if command_id == "ve_1202":
        enabled = kwargs.get("enabled")
        start_minutes = kwargs.get("start_minutes")
        duration_hours = kwargs.get("duration_hours")
        if enabled is not None:
            plan = build_charge_plan(
                switch_status=1 if enabled else 0,
                start_minutes=int(start_minutes or 480),
                duration_hours=int(duration_hours or 6),
            )
            return replace(
                data,
                scheduled_charge_enabled=enabled,
                charge_appoint_plan=plan,
            )
    return data


def _first(data: dict[str, Any], *keys: str) -> Any:
    """Return the first present, non-empty value for possible API keys."""
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _as_float(value: Any) -> float | None:
    """Convert numeric API values to float, preserving missing/malformed as None."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> bool | None:
    """Convert common API boolean representations to bool."""
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on", "locked", "charging"}:
            return True
        if normalized in {"false", "0", "no", "off", "unlocked", "not_charging"}:
            return False
    if isinstance(value, int | float):
        return bool(value)
    return None


def _normalize_tire_pressures(value: Any) -> dict[str, float | None] | None:
    """Normalize tire pressures to a string-keyed dict in bar."""
    if not isinstance(value, dict):
        return None
    return {str(key): _as_float(pressure) for key, pressure in value.items()}


def _kpa_to_bar(value: Any) -> float | None:
    """Convert tire pressure from kPa to bar."""
    kpa = _as_float(value)
    if kpa is None:
        return None
    return kpa * 0.01


def _tire_pressure_bar(payload: dict[str, Any], kpa_key: str, bar_key: str) -> float | None:
    """Return tire pressure in bar from kPa or a direct bar field."""
    return _kpa_to_bar(payload.get(kpa_key)) or _as_float(payload.get(bar_key))


def _state_on(value: Any) -> bool | None:
    """Return True when a realtime flag uses 1 for active."""
    if value in (None, ""):
        return None
    return str(value) == "1"


def _is_open(value: Any) -> bool | None:
    """Return True when a realtime door/window/trunk flag is not closed (0)."""
    if value in (None, ""):
        return None
    return str(value) != "0"


def _parse_charge_appoint_plan(raw: Any) -> dict[str, Any] | None:
    """Return the first chargeAppointPlans entry when present."""
    if raw in (None, ""):
        return None
    if isinstance(raw, str):
        try:
            raw = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return None
    if not isinstance(raw, list) or not raw:
        return None
    first = raw[0]
    return first if isinstance(first, dict) else None


def _plan_switch_on(plan: dict[str, Any] | None) -> bool | None:
    """Return whether the scheduled charge plan is enabled on the vehicle."""
    if plan is None:
        return None
    status = plan.get("switchStatus")
    if status in (None, ""):
        return None
    return str(status) == "1"
