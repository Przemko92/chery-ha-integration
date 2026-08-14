"""Button platform for locate, find-car and operational actions."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .command_exec import async_send_vehicle_command
from .coordinator import CheryEuropeDataUpdateCoordinator
from .entity import CheryEuropeEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe buttons from a config entry."""
    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        [
            CheryEuropeCommandButton(
                coordinator,
                ButtonEntityDescription(
                    key="locate",
                    name="Locate",
                    translation_key="locate",
                    icon="mdi:crosshairs-gps",
                ),
                entry,
                command_id="ve_1209",
            ),
            CheryEuropeCommandButton(
                coordinator,
                ButtonEntityDescription(
                    key="find_car",
                    name="Find car",
                    translation_key="find_car",
                    icon="mdi:car-search",
                ),
                entry,
                command_id="ve_1208",
            ),
            CheryEuropeActionButton(
                coordinator,
                ButtonEntityDescription(
                    key="wake",
                    name="Wake vehicle",
                    translation_key="wake",
                    icon="mdi:car-connected",
                ),
                entry,
                action=coordinator.async_wake,
            ),
            CheryEuropeActionButton(
                coordinator,
                ButtonEntityDescription(
                    key="refresh_position",
                    name="Refresh position",
                    translation_key="refresh_position",
                    icon="mdi:map-marker-radius",
                ),
                entry,
                action=coordinator.async_probe,
            ),
            CheryEuropeActionButton(
                coordinator,
                ButtonEntityDescription(
                    key="refresh_full_status",
                    name="Refresh full status",
                    translation_key="refresh_full_status",
                    icon="mdi:car-info",
                ),
                entry,
                action=coordinator.async_refresh_full_status,
            ),
        ]
    )


class CheryEuropeCommandButton(CheryEuropeEntity, ButtonEntity):
    """PIN-protected remote command button."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: ButtonEntityDescription,
        entry: ConfigEntry,
        command_id: str,
    ) -> None:
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        self._command_id = command_id
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}"

    async def async_press(self, **kwargs: Any) -> None:
        """Send the button command."""
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            kwargs,
            command_id=self._command_id,
        )


class CheryEuropeActionButton(CheryEuropeEntity, ButtonEntity):
    """Coordinator action button without duplicating command wiring."""

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: ButtonEntityDescription,
        entry: ConfigEntry,
        action: Callable[[], Awaitable[None]],
    ) -> None:
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        self._action = action
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}"

    async def async_press(self) -> None:
        """Run the configured coordinator action."""
        try:
            await self._action()
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "Chery Europe action %s failed",
                self.entity_description.key,
            )
