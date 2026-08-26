"""Select platform for the closed/vent-or-tilt/open window and sunroof control."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .command_exec import async_send_vehicle_command
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import CheryData
from .entity import CheryEuropeEntity

PARALLEL_UPDATES = 0

OPTION_CLOSED = "closed"
OPTION_OPEN = "open"


@dataclass(frozen=True, kw_only=True)
class CheryEuropeVentSelectEntityDescription(SelectEntityDescription):
    """Describes a closed/vent-or-tilt/open select for a window or the sunroof."""

    command_id: str
    position_fn: Callable[[CheryData], int | None]
    middle_option: str
    allow_middle_from_open: bool = True


def _window_group_position(data: CheryData) -> int | None:
    """Return the most-open position among the four windows (0/50/100)."""
    positions = [
        data.window_front_left_position,
        data.window_front_right_position,
        data.window_rear_left_position,
        data.window_rear_right_position,
    ]
    known = [position for position in positions if position is not None]
    if not known:
        return None
    return max(known)


VENT_SELECT_DESCRIPTIONS: tuple[CheryEuropeVentSelectEntityDescription, ...] = (
    CheryEuropeVentSelectEntityDescription(
        key="windows",
        name="Windows",
        translation_key="windows",
        icon="mdi:car-door",
        command_id="ve_1206",
        position_fn=_window_group_position,
        middle_option="vent",
    ),
    CheryEuropeVentSelectEntityDescription(
        key="sunroof",
        name="Sunroof",
        translation_key="sunroof",
        icon="mdi:car-select",
        command_id="ve_1207",
        position_fn=lambda data: data.sunroof_position,
        middle_option="tilt",
        allow_middle_from_open=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe vent selects from a config entry."""
    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        CheryEuropeVentSelect(coordinator, description, entry)
        for description in VENT_SELECT_DESCRIPTIONS
    )


class CheryEuropeVentSelect(CheryEuropeEntity, SelectEntity):
    """Closed/vent-or-tilt/open control for a window or the sunroof."""

    entity_description: CheryEuropeVentSelectEntityDescription

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: CheryEuropeVentSelectEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}_{description.middle_option}_select"

    @property
    def current_option(self) -> str | None:
        position = self.entity_description.position_fn(self.chery_data)
        if position == 0:
            return OPTION_CLOSED
        if position == 100:
            return OPTION_OPEN
        if position == 50:
            return self.entity_description.middle_option
        return None

    @property
    def options(self) -> list[str]:
        # The sunroof can't tilt directly from fully open; it must close first.
        if not self.entity_description.allow_middle_from_open and self.current_option == OPTION_OPEN:
            return [OPTION_CLOSED, OPTION_OPEN]
        return [OPTION_CLOSED, self.entity_description.middle_option, OPTION_OPEN]

    async def async_select_option(self, option: str) -> None:
        action = "close" if option == OPTION_CLOSED else option
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            {},
            command_id=self.entity_description.command_id,
            action=action,
        )
