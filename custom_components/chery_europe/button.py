"""Button platform for locate, find-car and operational actions."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .command_exec import async_send_vehicle_command
from .const import BUTTON
from .coordinator import CheryEuropeDataUpdateCoordinator
from .departure import (
    QUICK_DEPARTURE_MINUTES,
    async_cancel_departure_restore,
    async_set_departure,
    departure_days,
    departure_restore_at_iso,
    departure_snapshot,
    schedule_departure_restore,
)
from .entity import (
    CheryEuropeEntity,
    async_remove_unsupported,
    control_permissions,
    iter_entry_coordinators,
    keep_feature,
    stable_unique_id,
    vehicle_uid,
)

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)

#: Minutes ahead of the press that the quick departure button schedules.
DEPARTURE_SOON_MINUTES = QUICK_DEPARTURE_MINUTES

DEPARTURE_SOON_DESCRIPTION = ButtonEntityDescription(
    key="departure_in_15_min",
    name="Departure in 15 minutes",
    translation_key="departure_in_15_min",
    icon="mdi:car-clock",
)

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
    removed: list[str] = []
    entities: list[ButtonEntity] = []
    for coordinator in iter_entry_coordinators(entry):
        perms = control_permissions(coordinator)
        vin = vehicle_uid(coordinator, entry)
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
        if keep_feature(
            perms,
            "departure",
            f"{vin}_{DEPARTURE_SOON_DESCRIPTION.key}",
            removed,
        ):
            entities.append(CheryEuropeDepartureSoonButton(coordinator, entry))
    async_add_entities(entities)
    async_remove_unsupported(hass, BUTTON, removed)


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


def departure_soon_target(now: datetime) -> tuple[str, list[int]]:
    """Return the departure time and weekday list for a "in 15 minutes" press.

    The time is rounded down to the minute Home Assistant shows, and only the
    weekday of the press is added: the plan must fire today, not repeat.
    """
    target = (now + timedelta(minutes=DEPARTURE_SOON_MINUTES)).replace(
        second=0, microsecond=0
    )
    return f"{target:%H:%M}", [now.isoweekday()]


class CheryEuropeDepartureSoonButton(CheryEuropeEntity, ButtonEntity, RestoreEntity):
    """Move the departure plan 15 minutes out, armed, for the rest of today.

    One press does what would otherwise take three entities: it shifts the
    departure time, switches the plan on and adds the current weekday, so the
    car is prepared for a drive that starts soon.  The parameters in force
    when the button is pressed are put back automatically
    :data:`~.departure.QUICK_DEPARTURE_MINUTES` later, so the quick shift never
    outlives the drive it was meant for.

    The saved parameters and their deadline are published as state attributes,
    so a restart inside that window still restores the plan.
    """

    def __init__(
        self,
        coordinator: CheryEuropeDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the quick departure button."""
        super().__init__(coordinator, DEPARTURE_SOON_DESCRIPTION, entry)
        self._attr_translation_key = DEPARTURE_SOON_DESCRIPTION.translation_key
        self._attr_unique_id = stable_unique_id(
            entry, DEPARTURE_SOON_DESCRIPTION.key, coordinator
        )

    async def async_added_to_hass(self) -> None:
        """Resume a restore that was pending when Home Assistant stopped."""
        await super().async_added_to_hass()
        if getattr(self.coordinator, "departure_previous", None) is not None:
            return
        state = await self.async_get_last_state()
        attributes = (state.attributes or {}) if state else {}
        saved = attributes.get("departure_previous")
        if not isinstance(saved, dict) or not saved:
            return
        self.coordinator.departure_previous = dict(saved)
        deadline = attributes.get("departure_restore_at")
        parsed = dt_util.parse_datetime(deadline) if isinstance(deadline, str) else None
        remaining = 0.0
        if parsed is not None:
            remaining = max(0.0, (parsed - dt_util.utcnow()).total_seconds())
        schedule_departure_restore(self.coordinator, self._entry, delay=remaining)

    async def async_will_remove_from_hass(self) -> None:
        """Drop the timer; a reload reschedules it from the saved deadline."""
        async_cancel_departure_restore(self.coordinator, keep_deadline=True)
        await super().async_will_remove_from_hass()

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the saved parameters so they survive a restart."""
        previous = getattr(self.coordinator, "departure_previous", None)
        if not previous:
            return None
        return {
            "departure_previous": dict(previous),
            "departure_restore_at": departure_restore_at_iso(self.coordinator),
        }

    async def async_press(self, **kwargs: Any) -> None:
        """Schedule the departure 15 minutes from now and arm it for today.

        The parameters in force before the first press are kept, so a second
        press shifts the time again without losing what has to be restored.
        """
        took_snapshot = getattr(self.coordinator, "departure_previous", None) is None
        if took_snapshot:
            self.coordinator.departure_previous = departure_snapshot(
                self.coordinator
            )
        travel_time, weekday = departure_soon_target(dt_util.now())
        days = sorted(set(departure_days(self.coordinator)) | set(weekday))
        schedule_departure_restore(
            self.coordinator,
            self._entry,
            delay=QUICK_DEPARTURE_MINUTES * 60,
        )
        try:
            await async_set_departure(
                self.coordinator,
                self._entry,
                travel_time=travel_time,
                enabled=True,
                days=days,
            )
        except Exception:
            async_cancel_departure_restore(self.coordinator)
            if took_snapshot:
                self.coordinator.departure_previous = None
            raise
