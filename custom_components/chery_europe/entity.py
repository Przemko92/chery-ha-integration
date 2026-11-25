import hashlib
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import CheryData, vehicle_display_name
from .permissions import feature_enabled


class CheryEuropeEntity(CoordinatorEntity[CheryEuropeDataUpdateCoordinator]):
    """Base entity for Chery Europe."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description,
        entry: ConfigEntry | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        # Never assign None: newer HA reads device_class / placeholders
        # from entity_description without a null check.
        if description is not None:
            self.entity_description = description
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information enriched from the vehicle list."""
        data = self.chery_data
        model = data.vehicle_full_name or "Unknown"
        if _contains_vin(model, data.vin):
            model = "Unknown"
        device_key = getattr(self.coordinator, "device_id", None) or stable_id(self._entry)
        return DeviceInfo(
            identifiers={(DOMAIN, device_key)},
            name=vehicle_display_name(data),
            manufacturer="Chery",
            model=model,
            # The VIN is the only stable identifier a user can read off the car
            # itself, so it is surfaced as the device serial number. It stays out
            # of entity names, unique ids and the recorder — device registry only.
            serial_number=data.vin or None,
            configuration_url=data.vehicle_picture_url,
        )

    @property
    def chery_data(self) -> CheryData:
        """Return normalized Chery data."""
        return self.coordinator.data or CheryData()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success


def control_permissions(coordinator: CheryEuropeDataUpdateCoordinator) -> dict[int, int]:
    """Return the vehicle authority map, or empty when it was not loaded."""
    if getattr(coordinator, "_permissions_loaded", False):
        perms = getattr(coordinator, "permissions", None)
        return perms if isinstance(perms, dict) else {}
    api = getattr(coordinator, "api", None)
    perms = getattr(api, "permissions", None)
    return perms if isinstance(perms, dict) else {}


def iter_entry_coordinators(entry: ConfigEntry) -> list[CheryEuropeDataUpdateCoordinator]:
    """Return every vehicle coordinator for this config entry."""
    runtime = getattr(entry, "runtime_data", None)
    coordinators = getattr(runtime, "coordinators", None)
    if coordinators:
        return list(coordinators)
    if runtime is None:
        return []
    return [runtime]


def vehicle_slot(vin: str) -> str:
    """Stable device suffix that is not the VIN itself."""
    return hashlib.sha256(vin.encode()).hexdigest()[:8]


def stable_id(entry: ConfigEntry | None) -> str:
    """Return the config-entry id used in device and entity names."""
    entry_id = getattr(entry, "entry_id", None)
    return str(entry_id) if entry_id else "chery"


def stable_unique_id(
    entry: ConfigEntry | None,
    suffix: str,
    coordinator: CheryEuropeDataUpdateCoordinator | None = None,
) -> str:
    """Build a unique id that does not contain the vehicle VIN."""
    return f"{vehicle_uid(coordinator, entry)}_{suffix}"


def vehicle_uid(
    coordinator: CheryEuropeDataUpdateCoordinator | None,
    entry: ConfigEntry | None,
) -> str:
    """Return the stable prefix for entity unique ids."""
    base = stable_id(entry)
    slot = getattr(coordinator, "entity_slot", None) if coordinator is not None else None
    if slot:
        return f"{base}_{slot}"
    return base


def async_drop_vin_from_names(
    hass: HomeAssistant,
    entry: ConfigEntry,
    vin: str | None,
) -> None:
    """Rename registry entries so no device or entity name still contains the VIN."""
    if not vin or not vin.strip():
        return
    _rename_device(hass, entry, vin)
    _rename_entities(hass, entry, vin)
    title = getattr(entry, "title", None)
    if isinstance(title, str) and _contains_vin(title, vin):
        data = getattr(getattr(entry, "runtime_data", None), "data", None)
        hass.config_entries.async_update_entry(
            entry,
            title=vehicle_display_name(data) if data is not None else "Chery Vehicle",
        )


LEGACY_ENTITY_KEYS = (
    "last_message",
    "messages_content",
    "messages_history",
    "departure_restore",
)

# Entity ids are generated from the translated name only once, when the entity is
# first registered, so a renamed translation leaves the old slug behind forever.
# (domain, unique_id suffix, old slug, new slug)
# Unique-id suffixes that differ from the translation key of their entity.
UID_TRANSLATION_KEYS = {"charging_switch": "charging", "air_duration_select": "air_duration"}

ENTITY_ID_RENAMES = (
    # Messages and alarms.
    ("sensor", "alerts_content", "tresc_alarmow", "alarmy_tresc"),
    ("sensor", "messages_unread", "nieprzeczytane_wiadomosci", "wiadomosci_nieprzeczytane"),
    # Wheels.
    ("sensor", "tire_pressure_front_left", "cisnienie_przedniej_lewej_opony", "kolo_przednie_lewe_cisnienie"),
    ("sensor", "tire_pressure_front_right", "cisnienie_przedniej_prawej_opony", "kolo_przednie_prawe_cisnienie"),
    ("sensor", "tire_pressure_rear_left", "cisnienie_tylnej_lewej_opony", "kolo_tylne_lewe_cisnienie"),
    ("sensor", "tire_pressure_rear_right", "cisnienie_tylnej_prawej_opony", "kolo_tylne_prawe_cisnienie"),
    ("sensor", "tire_temperature_front_left", "temperatura_przedniej_lewej_opony", "kolo_przednie_lewe_temperatura"),
    ("sensor", "tire_temperature_front_right", "temperatura_przedniej_prawej_opony", "kolo_przednie_prawe_temperatura"),
    ("sensor", "tire_temperature_rear_left", "temperatura_tylnej_lewej_opony", "kolo_tylne_lewe_temperatura"),
    ("sensor", "tire_temperature_rear_right", "temperatura_tylnej_prawej_opony", "kolo_tylne_prawe_temperatura"),
    # Battery.
    ("sensor", "battery_level", "poziom_baterii", "bateria_poziom"),
    ("sensor", "battery_voltage_v", "napiecie_baterii_trakcyjnej", "bateria_napiecie"),
    ("sensor", "battery_current_a", "prad_baterii_trakcyjnej", "bateria_prad"),
    ("binary_sensor", "high_voltage", "uklad_wysokiego_napiecia", "bateria_wysokie_napiecie"),
    # Charging.
    ("sensor", "charging_power_kw", "moc_ladowania", "ladowanie_moc"),
    ("sensor", "remain_charge_time", "pozostaly_czas_ladowania", "ladowanie_pozostaly_czas"),
    ("sensor", "charge_status", "stan_ladowania", "ladowanie_stan"),
    ("sensor", "appointment_charge_status", "stan_zaplanowanego_ladowania", "ladowanie_stan_zaplanowany"),
    ("binary_sensor", "charging", "ladowanie", "ladowanie_trwa"),
    ("binary_sensor", "charge_gun_connected", "kabel_ladowania_podlaczony", "ladowanie_kabel_podlaczony"),
    ("binary_sensor", "fast_charge_gun_connected", "szybka_ladowarka_podlaczona", "ladowanie_szybka_ladowarka"),
    ("switch", "charging_switch", "ladowanie", "ladowanie_start"),
    ("switch", "scheduled_charging", "zaplanowane_ladowanie", "ladowanie_plan"),
    ("switch", "scheduled_charging", "ladowanie_zaplanowane", "ladowanie_plan"),
    ("binary_sensor", "appointment_charging", "zaplanowane_ladowanie", "ladowanie_plan"),
    ("binary_sensor", "appointment_charging", "ladowanie_zaplanowane", "ladowanie_plan"),
    ("time", "charge_start_time", "godzina_rozpoczecia_ladowania", "ladowanie_godzina_startu"),
    ("number", "charge_duration_hours", "czas_trwania_ladowania", "ladowanie_czas_trwania"),
    # Vehicle.
    ("sensor", "vehicle_nickname", "nazwa_pojazdu", "pojazd_nazwa"),
    ("sensor", "vehicle_full_name", "model_pojazdu", "pojazd_model"),
    ("sensor", "vehicle_color", "kolor_pojazdu", "pojazd_kolor"),
    ("sensor", "vehicle_picture", "zdjecie_pojazdu", "pojazd_zdjecie"),
    ("binary_sensor", "online", "online", "pojazd_online"),
    ("binary_sensor", "engine", "silnik", "pojazd_silnik"),
    # Climate.
    ("binary_sensor", "air_purification", "oczyszczanie_powietrza", "klimatyzacja_oczyszczanie_powietrza"),
    ("switch", "air_purification", "oczyszczanie_powietrza", "klimatyzacja_oczyszczanie_powietrza"),
    ("sensor", "climate_min_temperature", "minimalna_temperatura_klimatyzacji", "klimatyzacja_temperatura_min"),
    ("sensor", "climate_max_temperature", "maksymalna_temperatura_klimatyzacji", "klimatyzacja_temperatura_maks"),
    ("switch", "heat_everything", "grzej_wszystko", "klimatyzacja_hi"),
    ("switch", "heat_everything", "klimatyzacja_grzej_wszystko", "klimatyzacja_hi"),
    ("switch", "cool_everything", "chlodz_wszystko", "klimatyzacja_lo"),
    ("switch", "cool_everything", "klimatyzacja_chlodz_wszystko", "klimatyzacja_lo"),
    ("select", "air_duration_select", "czas_pracy_klimatyzacji", "klimatyzacja_czas_pracy"),
    ("select", "air_duration_select", "climate_runtime", "klimatyzacja_czas_pracy"),
    # Windows.
    ("switch", "front_windshield_heating", "ogrzewanie_przedniej_szyby", "szyba_przednia_ogrzewanie"),
    ("switch", "front_windshield_defrost", "odmrazanie_przedniej_szyby_nawiew", "szyba_przednia_odmrazanie"),
    ("switch", "front_windshield_defrost", "szyba_przednia_odmrazanie_nawiew", "szyba_przednia_odmrazanie"),
    ("switch", "rear_window_defrost", "ogrzewanie_tylnej_szyby", "szyba_tylna_ogrzewanie"),
    ("select", "windows", "szyby", "szyby_wszystkie"),
    ("select", "sunroof", "szyberdach", "szyberdach_pozycja"),
    # Doors, seats and steering wheel.
    ("lock", "doors", "drzwi", "drzwi_zamek"),
    ("switch", "steering_wheel_heating", "ogrzewanie_kierownicy", "kierownica_ogrzewanie"),
    ("select", "driver_seat_heating", "ogrzewanie_fotela_kierowcy", "fotel_kierowcy_ogrzewanie"),
    ("select", "passenger_seat_heating", "ogrzewanie_fotela_pasazera", "fotel_pasazera_ogrzewanie"),
    ("select", "driver_seat_ventilation", "wentylacja_fotela_kierowcy", "fotel_kierowcy_wentylacja"),
    ("select", "passenger_seat_ventilation", "wentylacja_fotela_pasazera", "fotel_pasazera_wentylacja"),
    ("select", "rear_left_seat_heating", "ogrzewanie_fotela_tylnego_lewego", "fotel_tylny_lewy_ogrzewanie"),
    ("select", "rear_right_seat_heating", "ogrzewanie_fotela_tylnego_prawego", "fotel_tylny_prawy_ogrzewanie"),
    ("select", "rear_left_seat_ventilation", "wentylacja_fotela_tylnego_lewego", "fotel_tylny_lewy_wentylacja"),
    ("select", "rear_right_seat_ventilation", "wentylacja_fotela_tylnego_prawego", "fotel_tylny_prawy_wentylacja"),
    # Alarms.
    ("switch", "theft_alarm", "alarm_antykradziezowy", "alarmy_antykradziezowy"),
    # Departures.
    ("sensor", "prepare_plans", "zaplanowane_przygotowanie", "wyjazd_plany"),
    ("sensor", "prepare_next_departure", "nastepny_wyjazd", "wyjazd_nastepny"),
    ("time", "departure_time", "godzina_wyjazdu", "wyjazd_godzina"),
    ("switch", "departure", "wyjazd_start", "wyjazd_plan"),
    # Buttons.
    ("button", "locate", "zlokalizuj", "pozycja_zlokalizuj"),
    ("button", "refresh_position", "odswiez_pozycje", "pozycja_odswiez"),
    ("button", "find_car", "znajdz_auto", "pojazd_znajdz"),
    ("button", "wake", "wybudz_auto", "pojazd_wybudz"),
    ("button", "refresh_full_status", "odswiez_pelny_status", "diagnostyka_odswiez_status"),
    ("button", "refresh_full_status", "status_odswiez", "diagnostyka_odswiez_status"),
    ("button", "departure_in_15_min", "wyjazd_za_15_minut", "wyjazd_za_15min"),
    ("button", "departure_in_15_min", "wyjazd_za_15_min", "wyjazd_za_15min"),
    # Ranges, consumption and diagnostics.
    ("sensor", "fuel_level", "pozostale_paliwo", "paliwo_poziom"),
    ("sensor", "range", "zasieg", "zasieg_laczny"),
    ("sensor", "fuel_range", "zasieg_na_paliwie", "zasieg_paliwo"),
    ("sensor", "odometer", "przebieg", "przebieg_laczny"),
    ("sensor", "electric_odometer", "przebieg_na_pradzie", "przebieg_elektryczny"),
    ("sensor", "fuel_consumption", "spalanie", "paliwo_spalanie"),
    ("sensor", "power_consumption", "zuzycie_pradu", "energia_zuzycie"),
    ("sensor", "vehicle_speed", "predkosc_pojazdu", "pojazd_predkosc"),
    ("sensor", "vehicle_speed", "predkosc", "pojazd_predkosc"),
    ("sensor", "last_data_update", "ostatnie_pobranie_danych", "diagnostyka_ostatnie_pobranie"),
    ("sensor", "command_status", "wynik_komendy", "diagnostyka_wynik_komendy"),
    ("sensor", "wake_status", "wynik_wybudzenia", "diagnostyka_wynik_wybudzenia"),
    ("sensor", "probe_status", "wynik_odczytu_pozycji", "diagnostyka_wynik_pozycji"),
)


def async_rename_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move entity ids still carrying an old translated slug to the current one."""
    registry = er.async_get(hass)
    for domain, key, old_slug, new_slug in ENTITY_ID_RENAMES:
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.domain != domain or not entity.unique_id.endswith(f"_{key}"):
                continue
            object_id = entity.entity_id.partition(".")[2]
            if not object_id.endswith(old_slug) or object_id.endswith(new_slug):
                continue
            new_id = f"{domain}.{object_id[: -len(old_slug)]}{new_slug}"
            if registry.async_get(new_id) is None:
                registry.async_update_entity(entity.entity_id, new_entity_id=new_id)


#: Entities that are controlled while the car is in use rather than configured
#: once, so they belong under "Controls" on the device page.
CONTROL_CATEGORY_KEYS = (
    "charge_start_time",
    "charge_end_time",
    "charge_duration_hours",
    "scheduled_charging",
    "departure",
    "departure_time",
    "departure_monday",
    "departure_tuesday",
    "departure_wednesday",
    "departure_thursday",
    "departure_friday",
    "departure_saturday",
    "departure_sunday",
)


def async_move_to_controls(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop the config category from the charging and departure entities.

    The category is copied into the entity registry when an entity is created
    for the first time, so removing it from the entity description only helps
    new installs: existing ones would keep the entities under "Configuration"
    for good.  Clearing the stored category moves them on the next setup.
    """
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.entity_category is None:
            continue
        if any(entity.unique_id.endswith(f"_{key}") for key in CONTROL_CATEGORY_KEYS):
            registry.async_update_entity(entity.entity_id, entity_category=None)


def async_remove_legacy_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Drop registry entries of entities the integration no longer provides.

    Renaming the ``key`` of an entity description changes its unique id, so the
    old entry stays in the registry as an unavailable orphan and has to be
    removed by hand in the UI.  Cleaning it up here keeps the device page tidy.
    """
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if any(entity.unique_id.endswith(f"_{key}") for key in LEGACY_ENTITY_KEYS):
            registry.async_remove(entity.entity_id)


def async_device_by_identifier(
    registry: dr.DeviceRegistry, identifier: str, entry_id: str | None
) -> dr.DeviceEntry | None:
    """Look a device up by its identifier, scoped to the config entry.

    ``async_get_device(identifiers=...)`` is deprecated because identifiers are
    no longer unique across config entries.  The scoped lookup takes the whole
    ``(domain, identifier)`` tuple plus the entry id; keep the old call only as a
    fallback for Home Assistant versions without it.
    """
    lookup = getattr(registry, "async_get_device_by_identifier", None)
    if lookup is not None and entry_id is not None:
        return lookup((DOMAIN, identifier), entry_id)
    return registry.async_get_device(identifiers={(DOMAIN, identifier)})


def _rename_device(hass: HomeAssistant, entry: ConfigEntry, vin: str) -> None:
    registry = dr.async_get(hass)
    device = async_device_by_identifier(registry, vin, entry.entry_id)
    if device is None:
        return
    identifiers = {
        identifier
        for identifier in device.identifiers
        if identifier != (DOMAIN, vin)
    }
    identifiers.add((DOMAIN, entry.entry_id))
    updates: dict[str, object] = {"new_identifiers": identifiers}
    if isinstance(device.name, str) and _contains_vin(device.name, vin):
        data = getattr(getattr(entry, "runtime_data", None), "data", None)
        updates["name"] = (
            vehicle_display_name(data) if data is not None else "Chery Vehicle"
        )
    if device.serial_number != vin:
        # The VIN belongs on the device page; older builds blanked it here.
        updates["serial_number"] = vin
    registry.async_update_device(device.id, **updates)


def _rename_entities(hass: HomeAssistant, entry: ConfigEntry, vin: str) -> None:
    registry = er.async_get(hass)
    prefix = f"{vin}_"
    replacement = f"{entry.entry_id}_"
    vin_slug = vin.lower()
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        changes: dict[str, str | None] = {}
        if entity.unique_id.startswith(prefix):
            changes["new_unique_id"] = replacement + entity.unique_id[len(prefix) :]
        domain, object_id = entity.entity_id.split(".", 1)
        if vin_slug in object_id:
            stripped = "_".join(part for part in object_id.replace(vin_slug, "").split("_") if part)
            if stripped:
                changes["new_entity_id"] = registry.async_generate_entity_id(domain, stripped)
        if isinstance(entity.name, str) and _contains_vin(entity.name, vin):
            changes["name"] = _strip_vin(entity.name, vin) or None
        if isinstance(entity.original_name, str) and _contains_vin(entity.original_name, vin):
            changes["original_name"] = _strip_vin(entity.original_name, vin) or None
        if changes:
            registry.async_update_entity(entity.entity_id, **changes)


def _contains_vin(value: str, vin: str | None) -> bool:
    if not vin:
        return False
    return vin.strip().lower() in value.strip().lower()


def _strip_vin(value: str, vin: str) -> str:
    cleaned = re.sub(re.escape(vin), "", value, flags=re.IGNORECASE)
    return re.sub(r"[\s_\-]+", " ", cleaned).strip(" _-")


def async_remove_unsupported(
    hass: HomeAssistant,
    domain: str,
    unique_ids: list[str],
) -> None:
    """Drop registry entries for controls this vehicle is not allowed to use."""
    if not unique_ids:
        return
    registry = er.async_get(hass)
    for unique_id in unique_ids:
        entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
        if entity_id is not None:
            registry.async_remove(entity_id)


def async_remove_moved_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    domain: str,
    keys: tuple[str, ...],
) -> None:
    """Drop registry entries of entities that moved to another domain.

    Changing the platform of an entity leaves the old registry entry behind as
    an unavailable orphan on the device page, so it has to be removed here.
    """
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == domain and any(
            entity.unique_id.endswith(f"_{key}") for key in keys
        ):
            registry.async_remove(entity.entity_id)


def keep_feature(
    perms: dict[int, int],
    key: str,
    unique_id: str,
    removed: list[str],
) -> bool:
    """Return True when the entity should be created, else queue its unique id."""
    if feature_enabled(perms, key):
        return True
    if perms:
        removed.append(unique_id)
    return False
