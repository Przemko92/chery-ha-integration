"""Button platform for locate, find-car and operational actions."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .command_exec import async_send_vehicle_command
from .coordinator import CheryEuropeDataUpdateCoordinator
from .entity import CheryEuropeEntity, iter_entry_coordinators, stable_unique_id

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)

# key, default name, translation key, icon, category, coordinator action
ACTION_BUTTONS: tuple[tuple[str, str, str, str, EntityCategory | None, str], ...] = (
    ("wake", "Wake vehicle", "wake", "mdi:car-connected", None, "async_wake"),
    (
        "refresh_position",
        "Refresh position",
        "refresh_position",
        "mdi:map-marker-radius",
        None,
        "async_probe",
    ),
    (
        "refresh_full_status",
        "Refresh full status",
        "refresh_full_status",
        "mdi:car-info",
        None,
        "async_refresh_full_status",
    ),
    (
        "message_read",
        "Message read",
        "message_read",
        "mdi:email-open-outline",
        None,
        "async_mark_messages_read",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe buttons from a config entry."""
    entities: list[ButtonEntity] = []
    for coordinator in iter_entry_coordinators(entry):
        entities.extend(
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
            ]
        )
        entities.extend(
            CheryEuropeActionButton(
                coordinator,
                ButtonEntityDescription(
                    key=key,
                    name=name,
                    translation_key=translation_key,
                    icon=icon,
                    entity_category=entity_category,
                ),
                entry,
                action=getattr(coordinator, action_attr),
            )
            for key, name, translation_key, icon, entity_category, action_attr in ACTION_BUTTONS
        )
    async_add_entities(entities)


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
        self._attr_unique_id = stable_unique_id(entry, description.key, coordinator)

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
        action: Callable[[], Awaitable[object]],
    ) -> None:
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        self._action = action
        self._attr_unique_id = stable_unique_id(entry, description.key, coordinator)

    async def async_press(self) -> None:
        """Run the configured coordinator action."""
        try:
            result = await self._action()
        except Exception:
            _LOGGER.exception(
                "Chery Europe action %s failed",
                self.entity_description.key,
            )
            return
        if result is False:
            raise HomeAssistantError(
                f"Chery Europe action {self.entity_description.key} failed"
            )
