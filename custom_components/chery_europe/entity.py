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


LEGACY_ENTITY_KEYS = ("last_message", "messages_content", "messages_history")


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
    no longer unique across config entries.  Keep the old call only as a
    fallback for Home Assistant versions without the scoped lookup.
    """
    lookup = getattr(registry, "async_get_device_by_identifier", None)
    if lookup is not None:
        return lookup(identifier, DOMAIN, config_entry_id=entry_id)
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
    if isinstance(device.serial_number, str) and _contains_vin(device.serial_number, vin):
        updates["serial_number"] = None
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
