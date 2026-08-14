"""Vehicle data models for the Chery Europe integration."""

from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleStatus:
    """Current status of a vehicle."""

    vin: str
    battery_level: float | None = None
    fuel_level: float | None = None
    range_km: float | None = None
    tire_pressures: dict | None = None
    interior_temperature: float | None = None
    exterior_temperature: float | None = None
    is_locked: bool | None = None
    is_charging: bool | None = None
    latitude: float | None = None
    longitude: float | None = None
    last_updated: str | None = None
    front_windshield_heating: bool | None = None
    rear_window_defrost: bool | None = None
    hvac_enabled: bool | None = None
    hvac_mode: str | None = None
    target_temperature: float | None = None
    vehicle_full_name: str | None = None
    vehicle_color_name_en: str | None = None
    vehicle_picture_url: str | None = None
    vehicle_nickname: str | None = None
    min_temperature: float | None = None
    max_temperature: float | None = None
