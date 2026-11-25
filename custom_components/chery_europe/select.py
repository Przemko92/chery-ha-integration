"""Select platform for window/sunroof position and the seat level controls."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .command_exec import async_send_vehicle_command
from .const import SELECT, SWITCH
from .coordinator import CheryEuropeDataUpdateCoordinator
from .data import SEAT_FIELD_TO_ATTR, CheryData
from .entity import (
    CheryEuropeEntity,
    async_remove_moved_entities,
    async_remove_unsupported,
    control_permissions,
    iter_entry_coordinators,
    keep_feature,
    stable_unique_id,
    vehicle_uid,
)
from .vehicle_commands import AIR_DURATION_OPTIONS

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
    """Set up the Chery Europe selects from a config entry."""
    removed: list[str] = []
    entities: list[SelectEntity] = []
    for coordinator in iter_entry_coordinators(entry):
        perms = control_permissions(coordinator)
        vin = vehicle_uid(coordinator, entry)
        entities.extend(
            CheryEuropeVentSelect(coordinator, description, entry)
            for description in VENT_SELECT_DESCRIPTIONS
            if keep_feature(
                perms,
                description.key,
                f"{vin}_{description.key}_{description.middle_option}_select",
                removed,
            )
        )
        for description in SEAT_SELECT_DESCRIPTIONS:
            suffix = f"{description.key}{SEAT_SELECT_SUFFIX}"
            if keep_feature(perms, description.key, f"{vin}_{suffix}", removed):
                entities.append(CheryEuropeSeatSelect(coordinator, description, entry))
        if keep_feature(perms, "hvac", f"{vin}_{AIR_DURATION_UNIQUE_SUFFIX}", removed):
            entities.append(
                CheryEuropeAirDurationSelect(coordinator, AIR_DURATION_DESCRIPTION, entry)
            )
    # The seat level controls used to be switches; drop those registry entries so
    # they do not stay behind as unavailable orphans next to the new selects.
    async_remove_moved_entities(hass, entry, SWITCH, SEAT_SELECT_KEYS)
    async_add_entities(entities)
    async_remove_unsupported(hass, SELECT, removed)


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
        self._attr_unique_id = stable_unique_id(
            entry,
            f"{description.key}_{description.middle_option}_select",
            coordinator,
        )

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


#: Seat level select options in the order Home Assistant shows them, with the
#: level the car expects for each (0 = off, 1-3 = heating/ventilation strength).
SEAT_LEVEL_OPTIONS: dict[str, int] = {
    "off": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}
SEAT_OPTION_BY_LEVEL = {level: option for option, level in SEAT_LEVEL_OPTIONS.items()}
#: Unique id suffix of the seat selects; distinct from the old switch entities.
SEAT_SELECT_SUFFIX = "_level_select"


@dataclass(frozen=True, kw_only=True)
class CheryEuropeSeatSelectEntityDescription(SelectEntityDescription):
    """Describes an off/low/medium/high select for one seat function."""

    command_id: str
    seat_field: str


SEAT_SELECT_DESCRIPTIONS: tuple[CheryEuropeSeatSelectEntityDescription, ...] = (
    CheryEuropeSeatSelectEntityDescription(
        key="driver_seat_heating",
        name="Driver seat heating",
        translation_key="driver_seat_heating",
        icon="mdi:car-seat-heater",
        command_id="ve_1204",
        seat_field="mSeatHeating",
    ),
    CheryEuropeSeatSelectEntityDescription(
        key="passenger_seat_heating",
        name="Passenger seat heating",
        translation_key="passenger_seat_heating",
        icon="mdi:car-seat-heater",
        command_id="ve_1204",
        seat_field="pSeatHeating",
    ),
    CheryEuropeSeatSelectEntityDescription(
        key="driver_seat_ventilation",
        name="Driver seat ventilation",
        translation_key="driver_seat_ventilation",
        icon="mdi:car-seat-cooler",
        command_id="ve_1204",
        seat_field="mSeatAiry",
    ),
    CheryEuropeSeatSelectEntityDescription(
        key="passenger_seat_ventilation",
        name="Passenger seat ventilation",
        translation_key="passenger_seat_ventilation",
        icon="mdi:car-seat-cooler",
        command_id="ve_1204",
        seat_field="pSeatAiry",
    ),
    CheryEuropeSeatSelectEntityDescription(
        key="rear_left_seat_heating",
        name="Rear left seat heating",
        translation_key="rear_left_seat_heating",
        icon="mdi:car-seat-heater",
        command_id="ve_1204",
        seat_field="blSeatHeating",
    ),
    CheryEuropeSeatSelectEntityDescription(
        key="rear_right_seat_heating",
        name="Rear right seat heating",
        translation_key="rear_right_seat_heating",
        icon="mdi:car-seat-heater",
        command_id="ve_1204",
        seat_field="brSeatHeating",
    ),
    CheryEuropeSeatSelectEntityDescription(
        key="rear_left_seat_ventilation",
        name="Rear left seat ventilation",
        translation_key="rear_left_seat_ventilation",
        icon="mdi:car-seat-cooler",
        command_id="ve_1204",
        seat_field="blSeatAiry",
    ),
    CheryEuropeSeatSelectEntityDescription(
        key="rear_right_seat_ventilation",
        name="Rear right seat ventilation",
        translation_key="rear_right_seat_ventilation",
        icon="mdi:car-seat-cooler",
        command_id="ve_1204",
        seat_field="brSeatAiry",
    ),
)

#: Keys of the seat level selects, used to clean up the old switch entities.
SEAT_SELECT_KEYS: tuple[str, ...] = tuple(
    description.key for description in SEAT_SELECT_DESCRIPTIONS
)


class CheryEuropeSeatSelect(CheryEuropeEntity, SelectEntity):
    """Off/low/medium/high control for one seat heating or ventilation function."""

    entity_description: CheryEuropeSeatSelectEntityDescription

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: CheryEuropeSeatSelectEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, description, entry)
        self._attr_unique_id = stable_unique_id(
            entry, f"{description.key}{SEAT_SELECT_SUFFIX}", coordinator
        )

    @property
    def _level(self) -> int | None:
        """Return the level the car reports for this seat function (0 = off)."""
        levels = self.chery_data.seat_levels
        if levels is None:
            return None
        attr = SEAT_FIELD_TO_ATTR.get(self.entity_description.seat_field)
        return levels.get(attr) if attr else None

    @property
    def current_option(self) -> str | None:
        level = self._level
        if level is None:
            return None
        return SEAT_OPTION_BY_LEVEL[min(3, max(0, level))]

    @property
    def options(self) -> list[str]:
        return list(SEAT_LEVEL_OPTIONS)

    async def async_select_option(self, option: str) -> None:
        level = SEAT_LEVEL_OPTIONS.get(option)
        if level is None:
            raise ValueError(f"Unsupported seat level: {option}")
        await async_send_vehicle_command(
            self.coordinator,
            self._entry,
            self.chery_data.vin,
            {},
            command_id=self.entity_description.command_id,
            seat_field=self.entity_description.seat_field,
            enabled=level > 0,
            level=level,
        )


AIR_DURATION_UNIQUE_SUFFIX = "air_duration_select"


@dataclass(frozen=True, kw_only=True)
class CheryEuropeAirDurationSelectEntityDescription(SelectEntityDescription):
    """Describes the air-conditioning runtime select."""


AIR_DURATION_DESCRIPTION = CheryEuropeAirDurationSelectEntityDescription(
    key="air_duration",
    name="Climate runtime",
    translation_key="air_duration",
    icon="mdi:timer-outline",
)


class CheryEuropeAirDurationSelect(CheryEuropeEntity, SelectEntity):
    """Pick the airControl ``times`` used when the climate is started remotely.

    The car accepts 5, 10 or 15 minutes in the ``times`` field of the
    airControl command; the value lives on the coordinator so the climate
    entity can send it with every start.
    """

    entity_description: CheryEuropeAirDurationSelectEntityDescription

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        description: CheryEuropeAirDurationSelectEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator, description, entry)
        self._attr_unique_id = stable_unique_id(
            entry, AIR_DURATION_UNIQUE_SUFFIX, coordinator
        )

    @property
    def current_option(self) -> str | None:
        """Return the runtime that will be sent with the next start."""
        return getattr(self.coordinator, "hvac_duration", None)

    @property
    def options(self) -> list[str]:
        """Return the runtimes the car accepts, in minutes."""
        return list(AIR_DURATION_OPTIONS)

    async def async_select_option(self, option: str) -> None:
        """Store the runtime for the next climate start."""
        if option not in AIR_DURATION_OPTIONS:
            raise ValueError(f"Unsupported climate runtime: {option}")
        self.coordinator.hvac_duration = option
        self.async_write_ha_state()
