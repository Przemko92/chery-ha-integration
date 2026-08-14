from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import CheryData, vehicle_display_name


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
        vin = data.vin or "unknown"
        return DeviceInfo(
            identifiers={(DOMAIN, vin)},
            name=vehicle_display_name(data),
            manufacturer="Chery",
            model=data.vehicle_full_name or "Unknown",
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
