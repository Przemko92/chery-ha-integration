"""Device tracker for Chery Europe GPS position."""

from __future__ import annotations

from homeassistant.components.device_tracker import (
    SourceType,
    TrackerEntity,
    TrackerEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import CheryEuropeDataUpdateCoordinator
from .entity import CheryEuropeEntity

PARALLEL_UPDATES = 0

POSITION_DESCRIPTION = TrackerEntityDescription(
    key="position",
    name="Position",
    translation_key="position",
    icon="mdi:car",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Chery Europe device tracker from a config entry."""
    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    async_add_entities([CheryEuropeDeviceTracker(coordinator, entry)])


class CheryEuropeDeviceTracker(CheryEuropeEntity, TrackerEntity, RestoreEntity):
    """GPS position of the vehicle."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, POSITION_DESCRIPTION, entry)
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{POSITION_DESCRIPTION.key}"
        self._restored_lat: float | None = None
        self._restored_lon: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._restored_lat = _as_float(last.attributes.get("latitude"))
            self._restored_lon = _as_float(last.attributes.get("longitude"))

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        return self.chery_data.latitude if self.chery_data.latitude is not None else self._restored_lat

    @property
    def longitude(self) -> float | None:
        return self.chery_data.longitude if self.chery_data.longitude is not None else self._restored_lon

    @property
    def extra_state_attributes(self) -> dict[str, float | str] | None:
        attrs: dict[str, float | str] = {}
        if self.chery_data.gps_time:
            attrs["gps_time"] = self.chery_data.gps_time
        if self.chery_data.gps_direction is not None:
            attrs["direction"] = self.chery_data.gps_direction
        if self.chery_data.gps_speed is not None:
            attrs["speed"] = self.chery_data.gps_speed
        return attrs or None


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
