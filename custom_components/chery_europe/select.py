"""Select platform for the closed/tilt/open sunroof control."""

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
OPTION_TILT = "tilt"
OPTION_OPEN = "open"
TILT_OPTIONS = [OPTION_CLOSED, OPTION_TILT, OPTION_OPEN]

POSITION_TO_OPTION = {0: OPTION_CLOSED, 50: OPTION_TILT, 100: OPTION_OPEN}
OPTION_TO_ACTION = {OPTION_CLOSED: "close", OPTION_TILT: "tilt", OPTION_OPEN: "open"}


@dataclass(frozen=True, kw_only=True)
class CheryEuropeTiltSelectEntityDescription(SelectEntityDescription):
    """Describes a closed/tilt/open select for the sunroof."""

    command_id: str
    position_fn: Callable[[CheryData], int | None]


TILT_SELECT_DESCRIPTIONS: tuple[CheryEuropeTiltSelectEntityDescription, ...] = (
    CheryEuropeTiltSelectEntityDescription(
        key="sunroof",
        name="Sunroof",
        translation_key="sunroof",
        icon="mdi:car-select",
        command_id="ve_1207",
        position_fn=lambda data: data.sunroof_position,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Chery Europe tilt selects from a config entry."""
    coordinator: CheryEuropeDataUpdateCoordinator = entry.runtime_data
    async_add_entities(
        CheryEuropeTiltSelect(coordinator, description, entry)
        for description in TILT_SELECT_DESCRIPTIONS
    )


class CheryEuropeTiltSelect(CheryEuropeEntity, SelectEntity):
    """Closed/tilt/open control for the sunroof."""

    entity_description: CheryEuropeTiltSelectEntityDescription

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: CheryEuropeTiltSelectEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, description, entry)
        self._attr_translation_key = description.translation_key
        vin = self.chery_data.vin or entry.entry_id
        self._attr_unique_id = f"{vin}_{description.key}_tilt_select"

    @property
    def current_option(self) -> str | None:
        position = self.entity_description.position_fn(self.chery_data)
        if position is None:
            return None
        return POSITION_TO_OPTION.get(position)

    @property
    def options(self) -> list[str]:
        # The sunroof can't tilt directly from fully open; it must close first.
        if self.current_option == OPTION_OPEN:
            return [OPTION_CLOSED, OPTION_OPEN]
        return TILT_OPTIONS

    async def async_select_option(self, option: str) -> None:
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            {},
            command_id=self.entity_description.command_id,
            action=OPTION_TO_ACTION[option],
        )
