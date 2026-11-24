import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CheryEuropeApi
from .const import (
    CONF_POLL_CHARGING,
    CONF_POLL_HV,
    CONF_POLL_NORMAL,
    DEFAULT_MQTT_HOST,
    DEFAULT_MQTT_PORT,
    DEFAULT_POLL_CHARGING_MIN,
    DEFAULT_POLL_HV_MIN,
    DEFAULT_POLL_NORMAL_MIN,
    DEFAULT_SESSION_KEEPALIVE,
    DOMAIN,
    DRIVE_WATCH_INTERVAL,
    MESSAGES_BACKFILL_MAX_PAGES,
    MESSAGES_BACKFILL_PAGE_SIZE,
    MESSAGES_POLL_INTERVAL,
    MESSAGES_POLL_PAGE_SIZE,
    MESSAGES_RESCAN_INTERVAL,
    POST_COMMAND_REFRESH_DELAYS,
    PREPARE_POLL_INTERVAL,
    REFRESH_HV_WAIT_SECONDS,
    STATUS_MAX_LEN,
)
from .data import (
    CheryData,
    apply_charge_appointment,
    apply_data_freshness,
    apply_location,
    apply_messages,
    apply_travel_appointment,
    is_command_ack,
    merge_chery_data,
    vehicle_display_name,
)
from .exceptions import (
    CheryEuropeAuthError,
    CheryEuropeCommandError,
    CheryEuropeException,
)
from .message_history import MessageHistory
from .messages import parse_messages, unread_count, unread_messages
from .mqtt import CheryEuropeMqttClient
from .pin import resolve_pin

_LOGGER = logging.getLogger(__name__)


def _vehicle_vin(vehicle: object) -> str | None:
    """Return a VIN from a vehicle-list row."""
    if isinstance(vehicle, dict):
        vin = vehicle.get("vin") or vehicle.get("VIN") or vehicle.get("vehicleVin")
    else:
        vin = getattr(vehicle, "vin", None)
    if vin in (None, ""):
        return None
    return str(vin)


def _select_vehicle(vehicles: list, vin_filter: str | None) -> object | None:
    """Pick the configured vehicle, or the first one on legacy entries."""
    if vin_filter:
        for vehicle in vehicles:
            if _vehicle_vin(vehicle) == vin_filter:
                return vehicle
        return None
    return vehicles[0]


def _payload_vin(payload: dict) -> str | None:
    """Return a VIN carried on an MQTT payload, if the cloud sent one."""
    if not isinstance(payload, dict):
        return None
    for key in ("vin", "VIN", "vehicleVin"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


_CONTROL_STATE_FIELDS = (
    "is_locked",
    "is_charging",
    "appointment_charge",
    "scheduled_charge_enabled",
    "charge_appoint_plan",
    "front_windshield_heating",
    "front_windshield_defrost",
    "rear_window_defrost",
    "steering_wheel_heating",
    "air_purification",
    "sunroof_open",
    "hvac_enabled",
    "hvac_mode",
    "target_temperature",
    "driver_seat_heating",
    "passenger_seat_heating",
    "driver_seat_ventilation",
    "passenger_seat_ventilation",
    "rear_left_seat_heating",
    "rear_right_seat_heating",
    "rear_left_seat_ventilation",
    "rear_right_seat_ventilation",
    "theft_alarm",
    "prepare_plans",
    "prepare_next_departure",
    "messages",
    "messages_total",
    "messages_unread",
    "messages_polled_at",
)


class CheryEuropeDataUpdateCoordinator(DataUpdateCoordinator[CheryData]):
    """Coordinate data updates for Chery Europe."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: CheryEuropeApi,
        entry: ConfigEntry,
        scan_interval: timedelta,
        *,
        vin: str | None = None,
        entity_slot: str | None = None,
        device_id: str | None = None,
        rename_entry: bool = True,
        owns_account_session: bool = True,
    ) -> None:
        self.api = api
        self.entry = entry
        self.vin_filter = vin
        self.entity_slot = entity_slot
        self.device_id = device_id
        self.rename_entry = rename_entry
        self.owns_account_session = owns_account_session
        self.permissions: dict[int, int] = {}
        self._prepare_polled_at: datetime | None = None
        self._messages_polled_at: datetime | None = None
        self._messages_rescanned_at: datetime | None = None
        # Created on the first inbox poll so a failed setup costs nothing.
        self._message_history: MessageHistory | None = None
        self._permissions_loaded = False
        self._mqtt_siblings: list = []
        self.charge_start_minutes = 480
        self.departure_draft: str | None = None
        self.departure_days: list[int] | None = None
        self.departure_armed: bool | None = None
        self.charge_duration_hours = 6
        self.poll_enabled = True
        self._mqtt: CheryEuropeMqttClient | None = None
        self._watch_unsub = None
        self._keepalive_unsub = None
        self._location_refresh_task = None
        self._wake_task: asyncio.Task | None = None
        self.update_poll_options(entry.options)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
            update_method=self._async_update_data,
        )

    def update_poll_options(self, options: dict | None = None) -> None:
        """Reload polling intervals from config entry options."""
        options = options or {}
        self.poll_normal_min = int(
            options.get(CONF_POLL_NORMAL, DEFAULT_POLL_NORMAL_MIN)
        )
        self.poll_charging_min = int(
            options.get(CONF_POLL_CHARGING, DEFAULT_POLL_CHARGING_MIN)
        )
        self.poll_hv_min = int(options.get(CONF_POLL_HV, DEFAULT_POLL_HV_MIN))

    def _update_status(self, **fields: str | None) -> None:
        """Merge operational status messages into coordinator data."""
        if self.data is None:
            return
        updates = {
            key: str(value)[:STATUS_MAX_LEN]
            for key, value in fields.items()
            if value is not None
        }
        if updates:
            self.async_set_updated_data(replace(self.data, **updates))

    async def _async_update_data(self) -> CheryData:
        """Fetch the latest data from Chery Europe."""
        try:
            vehicles = await self.api.get_vehicle_list()
            if not vehicles:
                return getattr(self, "data", None) or CheryData()
            first_vehicle = _select_vehicle(vehicles, self.vin_filter)
            if first_vehicle is None:
                _LOGGER.warning(
                    "Selected vehicle is not on this account; keeping the last reading"
                )
                return getattr(self, "data", None) or CheryData()
            if self.vin_filter is None and len(vehicles) > 1:
                _LOGGER.warning(
                    "Account has %s vehicles and this entry has no selection; using the first. "
                    "Remove and add the integration to choose which cars to monitor.",
                    len(vehicles),
                )
            vin = getattr(first_vehicle, "vin", None)
            if isinstance(first_vehicle, dict):
                vin = first_vehicle.get("vin")
            if not vin:
                data = CheryData.from_api_response(first_vehicle)
                self._sync_vehicle_identity(data)
                return self._publish_data(data)
            base = CheryData.from_api_response(first_vehicle)
            if not base.vin and vin:
                base = replace(base, vin=vin)
            try:
                self.permissions = await self.api.get_vehicle_authority(vin)
                self._permissions_loaded = True
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Vehicle permissions unavailable for %s: %s", vin, exc)
            try:
                realtime = await self.api.get_vehicle_status(vin)
            except Exception as exc:
                _LOGGER.debug(
                    "Vehicle realtime unavailable for %s; using list data only: %s",
                    vin,
                    exc,
                )
                self._sync_vehicle_identity(base)
                self._apply_scan_interval(base)
                base = await self._merge_charge_appointment(base)
                base = await self._merge_theft_alarm(base)
                base = await self._merge_messages(base)
                return self._publish_data(base)
            if not realtime:
                self._sync_vehicle_identity(base)
                self._apply_scan_interval(base)
                merged = await self._merge_location(base)
                merged = await self._merge_charge_appointment(merged)
                merged = await self._merge_travel_appointment(merged)
                merged = await self._merge_theft_alarm(merged)
                merged = await self._merge_messages(merged)
                return self._publish_data(merged)
            merged = merge_chery_data(
                base,
                CheryData.from_realtime(realtime, vin=vin),
            )
            merged = await self._merge_location(merged)
            merged = await self._merge_charge_appointment(merged)
            merged = await self._merge_travel_appointment(merged)
            merged = await self._merge_theft_alarm(merged)
            merged = await self._merge_messages(merged)
            self._sync_vehicle_identity(merged)
            self._apply_scan_interval(merged)
            return self._publish_data(merged)
        except CheryEuropeAuthError as exc:
            raise ConfigEntryAuthFailed("Chery Europe authentication failed") from exc
        except Exception as exc:
            _LOGGER.exception("Chery Europe data update failed")
            raise UpdateFailed("Failed to update Chery Europe data") from exc

    def _publish_data(self, data: CheryData) -> CheryData:
        """Preserve last-known fields and keep the data-age clock monotonic."""
        data = self._preserve_control_state(data)
        data = apply_data_freshness(getattr(self, "data", None), data)
        return self._preserve_status(data)

    def _preserve_status(self, data: CheryData) -> CheryData:
        """Keep operational status text when refreshing telemetry."""
        current = getattr(self, "data", None)
        if current is None:
            return data
        preserved = {}
        for field in ("command_status", "wake_status", "probe_status"):
            value = getattr(current, field)
            if value is not None and getattr(data, field) is None:
                preserved[field] = value
        if preserved:
            return replace(data, **preserved)
        return data

    def _preserve_control_state(self, data: CheryData) -> CheryData:
        """Keep last known control states when a refresh lacks realtime fields."""
        current = getattr(self, "data", None)
        if current is None:
            return data
        preserved = {}
        for field in _CONTROL_STATE_FIELDS:
            value = getattr(current, field)
            if value is not None and getattr(data, field) is None:
                preserved[field] = value
        if preserved:
            return replace(data, **preserved)
        return data

    def _sync_vehicle_identity(self, data: CheryData) -> None:
        """Keep the config entry and device names aligned with the vehicle nickname."""
        name = vehicle_display_name(data)
        if self.rename_entry and getattr(self.entry, "title", None) != name:
            self.hass.config_entries.async_update_entry(self.entry, title=name)

        device_registry = dr.async_get(self.hass)
        entry_id = getattr(self.entry, "entry_id", None)
        device_key = self.device_id or entry_id
        if not device_key:
            return
        # Imported here: entity.py imports this module, so a top-level import cycles.
        from .entity import async_device_by_identifier

        device = async_device_by_identifier(device_registry, device_key, entry_id)
        if device is not None and device.name != name:
            device_registry.async_update_device(device.id, name=name)

    def _poll_interval_for(self, data: CheryData) -> timedelta | None:
        """Return the configured poll interval for the current vehicle state."""
        if not self.poll_enabled:
            return None
        if data.charge_gun_connected or data.is_charging:
            minutes = self.poll_charging_min
            if minutes <= 0:
                minutes = self.poll_normal_min
        elif data.hv_high_voltage_on or data.engine_on:
            minutes = self.poll_hv_min
            if minutes <= 0:
                minutes = self.poll_normal_min
        else:
            minutes = self.poll_normal_min
        if minutes <= 0:
            return None
        return timedelta(minutes=minutes)

    def _apply_scan_interval(self, data: CheryData) -> None:
        """Poll faster while the vehicle is charging or the HV system is on."""
        self.update_interval = self._poll_interval_for(data)

    def schedule_refresh_after_command(self) -> None:
        """Schedule post-command refreshes without failing the caller."""
        self.hass.async_create_task(self._refresh_after_command_safe())

    def schedule_location_refresh(self) -> None:
        """Poll queryVehicleLocation after a locate command until GPS arrives."""
        task = self._location_refresh_task
        if task is not None and not task.done():
            return
        self._location_refresh_task = self.hass.async_create_task(
            self._async_refresh_location()
        )

    async def _merge_location(self, data: CheryData) -> CheryData:
        """Attach GPS from queryVehicleLocation when the vehicle is reachable."""
        if not data.vin:
            return data
        try:
            location = await self.api.get_vehicle_location(data.vin)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Vehicle location unavailable for %s: %s", data.vin, exc)
            return data
        if not location:
            return data
        return apply_location(data, location)

    async def _merge_charge_appointment(self, data: CheryData) -> CheryData:
        """Read the scheduled-charge plan. A failed query keeps the last plan."""
        if not data.vin:
            return data
        query = getattr(self.api, "query_charge_appointment", None)
        if query is None:
            return data
        try:
            result = await query(data.vin)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Charge appointment unavailable for %s: %s", data.vin, exc)
            return data
        return apply_charge_appointment(data, result)

    async def _merge_travel_appointment(self, data: CheryData) -> CheryData:
        """Read the scheduled cabin/battery preparation plans.

        Polled at most every ``PREPARE_POLL_INTERVAL`` so a short HV poll
        interval does not multiply the requests sent to the account. A failed
        query keeps the last plan list.
        """
        if not data.vin:
            return data
        now = datetime.now(UTC)
        last = self._prepare_polled_at
        if last is not None and now - last < PREPARE_POLL_INTERVAL:
            return data
        query = getattr(self.api, "query_travel_appointment", None)
        if query is None:
            return data
        try:
            plans = await query(data.vin)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Travel appointment unavailable for %s: %s", data.vin, exc)
            return data
        self._prepare_polled_at = now
        if plans is None:
            return data
        # prepareQuery answers [] on cars whose travel plans are write-only,
        # even right after a successful appointmentTravel write. Replacing a
        # list we already hold would drop every plan the next write does not
        # repeat.
        if not plans and data.prepare_plans:
            _LOGGER.debug(
                "Travel appointment query for %s returned no plans; keeping the last list",
                data.vin,
            )
            return data
        return apply_travel_appointment(data, plans, polled_at=now.isoformat())

    def invalidate_prepare_cache(self) -> None:
        """Force the next update to re-read the plans after we wrote them."""
        self._prepare_polled_at = None

    async def _fetch_all_messages(self) -> tuple[list[dict], int | None, bool]:
        """Read every inbox page once, newest first.

        Returns the messages, the total the server reports and whether the read
        completed.  Large pages are honoured by the endpoint, so a few hundred
        messages cost three requests instead of one per ten entries.
        """
        fetch = getattr(self.api, "fetch_messages", None)
        if fetch is None:
            return [], None, False
        messages: list[dict] = []
        total: int | None = None
        for page in range(1, MESSAGES_BACKFILL_MAX_PAGES + 1):
            try:
                payload = await fetch(page, MESSAGES_BACKFILL_PAGE_SIZE)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Vehicle messages page %s failed: %s", page, exc)
                return messages, total, False
            if payload is None:
                return messages, total, False
            chunk, page_total = parse_messages(payload)
            if page_total is not None:
                total = page_total
            if not chunk:
                break
            messages.extend(chunk)
            if total is not None and len(messages) >= total:
                break
            if len(chunk) < MESSAGES_BACKFILL_PAGE_SIZE:
                break
            await asyncio.sleep(1)
        return messages, total, True

    async def _merge_messages(self, data: CheryData) -> CheryData:
        """Read the message inbox into a stored history.

        The first run imports the complete inbox (a few large pages) so the
        whole conversation is available afterwards; later cycles only read the
        newest page and merge it by message id, at most every
        ``MESSAGES_POLL_INTERVAL``.  The cloud ``getUnread`` flag is compared
        with the locally counted unread entries -- messages read in the phone
        app flip their flag in the cloud, so a contradiction triggers one full
        rescan, at most once per ``MESSAGES_RESCAN_INTERVAL``.  A failed read
        keeps the stored history and the last state.
        """
        if not getattr(self, "owns_account_session", True):
            return await self._apply_shared_messages(data)

        now = datetime.now(UTC)
        last = self._messages_polled_at
        if last is not None and now - last < MESSAGES_POLL_INTERVAL:
            return data
        fetch = getattr(self.api, "fetch_messages", None)
        if fetch is None:
            return data
        history = self._message_history or self._create_message_history()
        await history.async_load()
        history.set_vin(data.vin)

        fetched = False
        total: int | None = None
        # Keep importing the whole inbox until one pass finishes. A failed
        # page used to leave a short history that later polls never extended,
        # because only an empty store took the full-import path.
        if history.is_empty or not history.backfilled_at:
            messages, total, complete = await self._fetch_all_messages()
            if messages:
                fetched = True
                history.merge(messages)
                if complete:
                    history.mark_backfilled(now.isoformat())
            elif complete:
                fetched = True
                history.mark_backfilled(now.isoformat())
        else:
            try:
                payload = await fetch(1, MESSAGES_POLL_PAGE_SIZE)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Vehicle messages unavailable: %s", exc)
                payload = None
            if payload is not None:
                chunk, page_total = parse_messages(payload)
                total = page_total
                fetched = True
                history.merge(chunk)

        unread: bool | None = None
        fetch_unread = getattr(self.api, "fetch_messages_unread", None)
        if fetch_unread is not None:
            try:
                unread = await fetch_unread()
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Unread messages flag unavailable: %s", exc)

        local_unread = unread_count(history.messages)
        if (
            unread is not None
            and bool(local_unread) != unread
            and self._may_rescan(now)
        ):
            _LOGGER.debug(
                "Unread flag (%s) disagrees with the stored history (%s); "
                "re-reading the inbox",
                unread,
                local_unread,
            )
            messages, rescan_total, _complete = await self._fetch_all_messages()
            self._messages_rescanned_at = now
            if messages:
                fetched = True
                total = rescan_total or total
                history.merge(messages)
                local_unread = unread_count(history.messages)

        # A failed read must not start the 30 minute throttle, or the first
        # outage hides the inbox until the next interval.
        if fetched:
            self._messages_polled_at = now
        await history.async_save()
        items = history.messages
        if not items and not fetched:
            return data
        if total is not None:
            total = max(total, len(items))
        return apply_messages(
            data,
            items,
            total=total,
            unread=unread,
            unread_count=local_unread,
            polled_at=now.isoformat() if fetched else None,
            backfilled_at=history.backfilled_at,
        )

    async def async_messages_page(
        self,
        page: int = 1,
        page_size: int = 50,
        *,
        unread_only: bool = False,
    ) -> dict[str, Any]:
        """Return one page of the stored history; never asks the cloud."""
        history = self._message_history or self._create_message_history()
        await history.async_load()
        items = unread_messages(history.messages) if unread_only else history.messages
        total = len(items)
        page_size = max(1, page_size)
        pages = max(1, -(-total // page_size))
        page = min(max(1, page), pages)
        start = (page - 1) * page_size
        return {
            "total": total,
            "page": page,
            "pages": pages,
            "page_size": page_size,
            "backfilled_at": history.backfilled_at,
            "messages": items[start : start + page_size],
        }

    async def async_mark_messages_read(self) -> bool:
        """Mark the inbox read in the cloud and in the stored history.

        Everything here is user triggered: one cloud call per button press,
        then the local history is flagged in place so the unread entities drop
        to zero right away instead of waiting for the next message poll.
        """
        mark = getattr(self.api, "mark_messages_read", None)
        if mark is None:
            return False
        try:
            accepted = await mark()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Marking the inbox read failed: %s", exc)
            return False
        if not accepted:
            return False
        history = self._message_history or self._create_message_history()
        await history.async_load()
        if history.mark_all_read():
            await history.async_save()
        data = self.data
        if data is None:
            return True
        self.async_set_updated_data(
            apply_messages(
                data,
                history.messages,
                total=data.messages_total,
                unread=False,
                unread_count=unread_count(history.messages),
                polled_at=data.messages_polled_at,
                backfilled_at=history.backfilled_at,
            )
        )
        return True

    async def _apply_shared_messages(self, data: CheryData) -> CheryData:
        """Copy the account inbox onto this vehicle without polling it again.

        The message centre is per account, not per VIN. Only the coordinator
        that owns the account session talks to it; the other vehicles on the
        same login show that one history.
        """
        history = self._message_history or self._create_message_history()
        await history.async_load()
        if history.is_empty and not history.backfilled_at:
            return data
        return apply_messages(
            data,
            history.messages,
            total=len(history.messages),
            unread_count=unread_count(history.messages),
            backfilled_at=history.backfilled_at,
        )

    def _create_message_history(self) -> MessageHistory:
        """Return the one on-disk inbox history for this config entry.

        Several vehicles share the entry. A history object per coordinator,
        all writing the same store key, kept overwriting each other.
        """
        entry_id = str(getattr(self.entry, "entry_id", "") or "default")
        root = self.hass.data.setdefault(DOMAIN, {})
        if not isinstance(root, dict):
            root = {}
            self.hass.data[DOMAIN] = root
        histories = root.setdefault("message_histories", {})
        history = histories.get(entry_id)
        if history is None:
            history = MessageHistory(self.hass, entry_id)
            histories[entry_id] = history
        self._message_history = history
        return history

    def _may_rescan(self, now: datetime) -> bool:
        """Return whether a full inbox rescan is allowed by the throttle."""
        last = self._messages_rescanned_at
        return last is None or now - last >= MESSAGES_RESCAN_INTERVAL

    async def _merge_theft_alarm(self, data: CheryData) -> CheryData:
        """Read the theft-alarm switch. A failed query keeps the last state."""
        if not data.vin:
            return data
        query = getattr(self.api, "query_theft_alarm", None)
        if query is None:
            return data
        try:
            state = await query(data.vin)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Theft alarm unavailable: %s", exc)
            return data
        if state is None:
            return data
        return replace(data, theft_alarm=state)

    async def _async_refresh_location(self) -> None:
        """Retry location reads after vehicleLocation has woken the car."""
        for delay in (2, 5, 10, 20):
            await asyncio.sleep(delay)
            if self.data is None or not self.data.vin:
                return
            updated = await self._merge_location(self.data)
            if updated.latitude is not None and updated.longitude is not None:
                if updated is not self.data:
                    self.async_set_updated_data(self._publish_data(updated))
                self._update_status(probe_status="Position updated ✅")
                return

    async def _refresh_after_command_safe(self) -> None:
        for delay in POST_COMMAND_REFRESH_DELAYS:
            await asyncio.sleep(delay)
            try:
                await self.async_request_refresh()
            except Exception as exc:
                _LOGGER.debug("Post-command refresh failed: %s", exc)

    async def async_wake(self) -> None:
        """Wake the vehicle with a benign locate request."""
        await self._run_wake_task()

    async def _run_wake_task(self) -> None:
        task = self._wake_task
        if task is not None and not task.done():
            await asyncio.shield(task)
            return
        self._wake_task = asyncio.create_task(self._async_wake_once())
        try:
            await asyncio.shield(self._wake_task)
        finally:
            if self._wake_task is not None and self._wake_task.done():
                self._wake_task = None

    async def _async_wake_once(self) -> None:
        vin = self.data.vin if self.data else None
        if not vin:
            raise HomeAssistantError("Vehicle is unavailable")
        self._update_status(wake_status="Sending wake request…")
        try:
            pin = resolve_pin(self.entry)
            response = await self.api.send_command(vin, "ve_1209", pin)
            if not response.get("ok"):
                message = response.get("message") or response.get("code")
                raise CheryEuropeCommandError(f"Chery Europe command failed: {message}")
            self._update_status(wake_status="Wake request sent ✅")
            self.schedule_location_refresh()
            self.schedule_refresh_after_command()
        except CheryEuropeException as exc:
            self._update_status(wake_status=f"Wake failed ❌: {exc}")
            raise
        except Exception as exc:
            self._update_status(wake_status=f"Wake failed ❌: {exc}")
            raise HomeAssistantError("Failed to wake Chery Europe vehicle") from exc

    async def async_probe(self) -> None:
        """Read GPS through queryVehicleLocation and refresh telemetry."""
        vin = self.data.vin if self.data else None
        if not vin:
            raise HomeAssistantError("Vehicle is unavailable")
        self._update_status(probe_status="Reading vehicle position…")
        try:
            updated = await self._merge_location(self.data)
            if updated.latitude is not None and updated.longitude is not None:
                self.async_set_updated_data(self._publish_data(updated))
                self._update_status(probe_status="Position updated ✅")
                return
            pin = resolve_pin(self.entry)
            response = await self.api.send_command(vin, "ve_1209", pin)
            if not response.get("ok"):
                message = response.get("message") or response.get("code")
                raise CheryEuropeCommandError(f"Chery Europe command failed: {message}")
            self.schedule_location_refresh()
            self._update_status(probe_status="Locate sent — waiting for GPS fix… ⏳")
        except CheryEuropeException as exc:
            self._update_status(probe_status=f"Position read failed ❌: {exc}")
            raise
        except Exception as exc:
            self._update_status(probe_status=f"Position read failed ❌: {exc}")
            raise HomeAssistantError("Failed to read Chery Europe position") from exc

    async def async_refresh_full_status(self) -> None:
        """Refresh odometer/battery with a brief climate wake when HV is off."""
        vin = self.data.vin if self.data else None
        if not vin:
            raise HomeAssistantError("Vehicle is unavailable")
        self._update_status(probe_status="Refreshing full vehicle status…")
        try:
            await self.async_request_refresh()
            if self._is_hv_on():
                self._update_status(probe_status="Full status updated ✅")
                return

            pin = resolve_pin(self.entry)
            self._update_status(
                probe_status="Turning climate on briefly to read real HV data… ⏳"
            )
            response = await self.api.send_command(
                vin,
                "ve_1104",
                pin,
                enabled=True,
                temperature=22.0,
            )
            if not response.get("ok"):
                message = response.get("message") or response.get("code")
                raise CheryEuropeCommandError(f"Chery Europe command failed: {message}")

            got = False
            for _ in range(6):
                await asyncio.sleep(REFRESH_HV_WAIT_SECONDS / 6)
                await self.async_request_refresh()
                if self._is_hv_on():
                    got = True
                    break

            try:
                await self.api.send_command(vin, "ve_1104", pin, enabled=False)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.debug("Climate off after refresh failed: %s", exc)

            if got:
                self._update_status(probe_status="Full status updated ✅")
            else:
                self._update_status(
                    probe_status="Vehicle did not wake in time — try again later ⏳"
                )
        except CheryEuropeException as exc:
            self._update_status(probe_status=f"Full refresh failed ❌: {exc}")
            raise
        except Exception as exc:
            self._update_status(probe_status=f"Full refresh failed ❌: {exc}")
            raise HomeAssistantError("Failed to refresh Chery Europe status") from exc

    def _is_hv_on(self) -> bool:
        if self.data is None:
            return False
        return bool(self.data.hv_high_voltage_on or self.data.engine_on)

    async def async_start_live_updates(self) -> None:
        """Start MQTT push, drive-watch poller, and session keep-alive."""
        if self.owns_account_session:
            await self.hass.async_add_executor_job(self._start_mqtt)
            self.async_start_keepalive()
        if self._watch_unsub is None:
            self._watch_unsub = async_track_time_interval(
                self.hass,
                self._async_drive_watch,
                DRIVE_WATCH_INTERVAL,
            )

    def async_start_keepalive(self) -> None:
        """Refresh OAuth tokens before they expire so reload stays OTP-free."""
        if self._keepalive_unsub is not None:
            return
        self._keepalive_unsub = async_track_time_interval(
            self.hass,
            self._async_keepalive,
            DEFAULT_SESSION_KEEPALIVE,
        )

    async def _async_keepalive(self, _now) -> None:
        """Proactively rotate tokens while the session is still valid."""
        try:
            refreshed = await self.api.ensure_fresh_token()
            if refreshed:
                _LOGGER.debug("Chery Europe session token refreshed by keep-alive")
        except CheryEuropeAuthError as exc:
            # Do not raise ConfigEntryAuthFailed from the timer: a transient
            # rejection should surface on the next coordinator poll instead of
            # immediately forcing OTP. Network-looking failures are also logged.
            _LOGGER.warning("Chery Europe keep-alive refresh failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Chery Europe keep-alive error (non-fatal): %s", exc)

    def _start_mqtt(self) -> None:
        t_user_id = self.api.t_user_id
        if not t_user_id:
            return
        certs_dir = self.hass.config.path(f"{DOMAIN}_{t_user_id}_certs")
        client = CheryEuropeMqttClient(
            host=DEFAULT_MQTT_HOST,
            port=DEFAULT_MQTT_PORT,
            t_user_id=t_user_id,
            channel_id=self.api.channel_id,
            certs_dir=certs_dir,
            on_payload=self._handle_mqtt_payload,
        )
        if client.start():
            self._mqtt = client

    def _handle_mqtt_payload(self, service: str, payload: dict) -> None:
        self.hass.loop.call_soon_threadsafe(self._apply_mqtt_payload, service, payload)

    def _apply_mqtt_payload(
        self, service: str, payload: dict, *, routed: bool = False
    ) -> None:
        if self.data is None:
            return
        incoming = _payload_vin(payload)
        if not routed and incoming and self._mqtt_siblings:
            for sibling in self._mqtt_siblings:
                target = sibling.vin_filter or (
                    sibling.data.vin if sibling.data else None
                )
                if target == incoming:
                    sibling._apply_mqtt_payload(service, payload, routed=True)
                    return
            return
        mine = self.vin_filter or self.data.vin
        if incoming and mine and incoming != mine:
            return
        located = apply_location(self.data, payload)
        if located is not self.data:
            self.async_set_updated_data(self._publish_data(located))
            if service == "1301" or is_command_ack(payload):
                return
        elif service == "1301":
            self.schedule_location_refresh()
            return
        if is_command_ack(payload):
            return
        realtime = CheryData.from_realtime(payload, vin=self.data.vin)
        merged = merge_chery_data(self.data, realtime)
        self._apply_scan_interval(merged)
        self.async_set_updated_data(self._publish_data(merged))

    async def _async_drive_watch(self, _now) -> None:
        """Cheap realtime check while parked so a trip or charge is noticed quickly."""
        if not self.poll_enabled or self.data is None or not self.data.vin:
            return
        interval = self._poll_interval_for(self.data)
        if interval is not None and interval <= timedelta(minutes=self.poll_hv_min):
            return
        try:
            realtime = await self.api.get_vehicle_status(self.data.vin)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Drive-watch realtime failed: %s", exc)
            return
        if not realtime:
            return
        merged = merge_chery_data(
            self.data,
            CheryData.from_realtime(realtime, vin=self.data.vin),
        )
        self._apply_scan_interval(merged)
        self.async_set_updated_data(self._publish_data(merged))

    async def async_stop_live_updates(self) -> None:
        """Stop MQTT, drive-watch, and session keep-alive timers."""
        if self._keepalive_unsub is not None:
            self._keepalive_unsub()
            self._keepalive_unsub = None
        if self._watch_unsub is not None:
            self._watch_unsub()
            self._watch_unsub = None
        mqtt = self._mqtt
        self._mqtt = None
        if mqtt is not None:
            await self.hass.async_add_executor_job(mqtt.stop)


class CheryEuropeRuntime:
    """One account session shared by every selected vehicle."""

    def __init__(self, coordinators: list[CheryEuropeDataUpdateCoordinator]) -> None:
        self.coordinators = coordinators
        if len(coordinators) > 1:
            for coordinator in coordinators:
                coordinator._mqtt_siblings = coordinators

    @property
    def api(self) -> CheryEuropeApi | None:
        if not self.coordinators:
            return None
        return self.coordinators[0].api

    @property
    def data(self) -> CheryData | None:
        if not self.coordinators:
            return None
        return self.coordinators[0].data

    @property
    def last_update_success(self) -> bool | None:
        if not self.coordinators:
            return None
        return all(
            getattr(item, "last_update_success", False) for item in self.coordinators
        )

    @property
    def last_update_success_time(self):
        times = [
            getattr(item, "last_update_success_time", None)
            for item in self.coordinators
        ]
        present = [item for item in times if item is not None]
        return max(present) if present else None

    async def async_start_live_updates(self) -> None:
        for coordinator in self.coordinators:
            await coordinator.async_start_live_updates()

    async def async_stop_live_updates(self) -> None:
        for coordinator in self.coordinators:
            await coordinator.async_stop_live_updates()

    def update_poll_options(self, options: dict | None = None) -> None:
        for coordinator in self.coordinators:
            coordinator.update_poll_options(options)
            if coordinator.data is not None:
                coordinator._apply_scan_interval(coordinator.data)
