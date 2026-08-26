"""Cover platform for the trunk."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityDescription,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .command_exec import async_send_vehicle_command
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import CheryData
from .entity import CheryEuropeEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class CheryEuropeCoverEntityDescription(CoverEntityDescription):
    """Describes a Chery Europe cover."""

    command_id: str
    is_open_fn: Callable[[CheryData], bool | None]


COVER_DESCRIPTIONS: tuple[CheryEuropeCoverEntityDescription, ...] = (
    CheryEuropeCoverEntityDescription(
        key="trunk",
        name="Trunk",
        translation_key="trunk",
        device_class=CoverDeviceClass.DOOR,
        icon="mdi:car-back",
        command_id="ve_1205",
        is_open_fn=lambda data: data.trunk_open,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe covers from a config entry."""
    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        CheryEuropeCover(coordinator, description, entry)
        for description in COVER_DESCRIPTIONS
    )


class CheryEuropeCover(CheryEuropeEntity, CoverEntity):
    """Motorized trunk."""

    entity_description: CheryEuropeCoverEntityDescription
    _attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: CheryEuropeCoverEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}_cover"

    @property
    def is_closed(self) -> bool | None:
        opened = self.entity_description.is_open_fn(self.chery_data)
        if opened is None:
            return None
        return not opened

    async def async_open_cover(self, **kwargs: Any) -> None:
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            kwargs,
            command_id=self.entity_description.command_id,
            action="open",
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            kwargs,
            command_id=self.entity_description.command_id,
            action="close",
        )
