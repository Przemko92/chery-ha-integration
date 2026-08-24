from dataclasses import replace
from datetime import timedelta
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

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
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SESSION_KEEPALIVE,
    DOMAIN,
    DRIVE_WATCH_INTERVAL,
    POST_COMMAND_REFRESH_DELAYS,
    REFRESH_HV_WAIT_SECONDS,
    STATUS_MAX_LEN,
)
from .data import CheryData, apply_location, is_command_ack, merge_chery_data, vehicle_display_name
from .exceptions import CheryEuropeAuthError, CheryEuropeCommandError, CheryEuropeException
from .mqtt import CheryEuropeMqttClient
from .pin import resolve_pin

_LOGGER = logging.getLogger(__name__)

_CONTROL_STATE_FIELDS = (
    "is_locked",
    "is_charging",
    "appointment_charge",
    "scheduled_charge_enabled",
    "charge_appoint_plan",
    "front_windshield_heating",
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
)


class CheryEuropeDataUpdateCoordinator(DataUpdateCoordinator[CheryData]):
    """Coordinate data updates for Chery Europe."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: CheryEuropeApi,
        entry: ConfigEntry,
        scan_interval: timedelta,
    ) -> None:
        self.api = api
        self.entry = entry
        self.charge_start_minutes = 480
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
            if len(vehicles) > 1:
                _LOGGER.warning(
                    "Account has %s vehicles; Chery Europe currently monitors only the first one",
                    len(vehicles),
                )
            first_vehicle = vehicles[0]
            vin = getattr(first_vehicle, "vin", None)
            if isinstance(first_vehicle, dict):
                vin = first_vehicle.get("vin")
            if not vin:
                data = CheryData.from_api_response(first_vehicle)
                self._sync_vehicle_identity(data)
                return self._preserve_status(data)
            base = CheryData.from_api_response(first_vehicle)
            if not base.vin and vin:
                base = replace(base, vin=vin)
            try:
                await self.api.get_vehicle_authority(vin)
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
                return self._preserve_control_state(self._preserve_status(base))
            if not realtime:
                self._sync_vehicle_identity(base)
                self._apply_scan_interval(base)
                merged = await self._merge_location(base)
                return self._preserve_control_state(self._preserve_status(merged))
            merged = merge_chery_data(
                base,
                CheryData.from_realtime(realtime, vin=vin),
            )
            merged = await self._merge_location(merged)
            self._sync_vehicle_identity(merged)
            self._apply_scan_interval(merged)
            return self._preserve_control_state(self._preserve_status(merged))
        except CheryEuropeAuthError as exc:
            raise ConfigEntryAuthFailed("Chery Europe authentication failed") from exc
        except Exception as exc:
            _LOGGER.exception("Chery Europe data update failed")
            raise UpdateFailed("Failed to update Chery Europe data") from exc

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
        if not data.vin:
            return

        name = vehicle_display_name(data)
        if getattr(self.entry, "title", None) != name:
            self.hass.config_entries.async_update_entry(self.entry, title=name)

        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, data.vin)})
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

    async def _async_refresh_location(self) -> None:
        """Retry location reads after vehicleLocation has woken the car."""
        for delay in (2, 5, 10, 20):
            await asyncio.sleep(delay)
            if self.data is None or not self.data.vin:
                return
            updated = await self._merge_location(self.data)
            if updated.latitude is not None and updated.longitude is not None:
                if updated is not self.data:
                    self.async_set_updated_data(self._preserve_status(updated))
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
            raise HomeAssistantError("Vehicle VIN is unavailable")
        self._update_status(wake_status="Sending wake request…")
        try:
            pin = resolve_pin(self.entry)
            response = await self.api.send_command(vin, "ve_1209", pin)
            if not response.get("ok"):
                message = response.get("message") or response.get("code")
                raise CheryEuropeCommandError(
                    f"Chery Europe command failed: {message}"
                )
            self._update_status(wake_status="Wake request sent ✅")
            self.schedule_location_refresh()
            self.schedule_refresh_after_command()
        except CheryEuropeException as exc:
            self._update_status(wake_status=f"Wake failed ❌: {exc}")
            raise
        except Exception as exc:  # noqa: BLE001
            self._update_status(wake_status=f"Wake failed ❌: {exc}")
            raise HomeAssistantError("Failed to wake Chery Europe vehicle") from exc

    async def async_probe(self) -> None:
        """Read GPS through queryVehicleLocation and refresh telemetry."""
        vin = self.data.vin if self.data else None
        if not vin:
            raise HomeAssistantError("Vehicle VIN is unavailable")
        self._update_status(probe_status="Reading vehicle position…")
        try:
            updated = await self._merge_location(self.data)
            if updated.latitude is not None and updated.longitude is not None:
                self.async_set_updated_data(self._preserve_status(updated))
                self._update_status(probe_status="Position updated ✅")
                return
            pin = resolve_pin(self.entry)
            response = await self.api.send_command(vin, "ve_1209", pin)
            if not response.get("ok"):
                message = response.get("message") or response.get("code")
                raise CheryEuropeCommandError(
                    f"Chery Europe command failed: {message}"
                )
            self.schedule_location_refresh()
            self._update_status(
                probe_status="Locate sent — waiting for GPS fix… ⏳"
            )
        except CheryEuropeException as exc:
            self._update_status(probe_status=f"Position read failed ❌: {exc}")
            raise
        except Exception as exc:  # noqa: BLE001
            self._update_status(probe_status=f"Position read failed ❌: {exc}")
            raise HomeAssistantError("Failed to read Chery Europe position") from exc

    async def async_refresh_full_status(self) -> None:
        """Refresh odometer/battery with a brief climate wake when HV is off."""
        vin = self.data.vin if self.data else None
        if not vin:
            raise HomeAssistantError("Vehicle VIN is unavailable")
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
                raise CheryEuropeCommandError(
                    f"Chery Europe command failed: {message}"
                )

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
        except Exception as exc:  # noqa: BLE001
            self._update_status(probe_status=f"Full refresh failed ❌: {exc}")
            raise HomeAssistantError("Failed to refresh Chery Europe status") from exc

    def _is_hv_on(self) -> bool:
        if self.data is None:
            return False
        return bool(self.data.hv_high_voltage_on or self.data.engine_on)

    async def async_start_live_updates(self) -> None:
        """Start MQTT push, drive-watch poller, and session keep-alive."""
        await self.hass.async_add_executor_job(self._start_mqtt)
        if self._watch_unsub is None:
            self._watch_unsub = async_track_time_interval(
                self.hass,
                self._async_drive_watch,
                DRIVE_WATCH_INTERVAL,
            )
        self.async_start_keepalive()

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

    def _apply_mqtt_payload(self, service: str, payload: dict) -> None:
        if self.data is None:
            return
        located = apply_location(self.data, payload)
        if located is not self.data:
            self.async_set_updated_data(self._preserve_status(located))
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
        self.async_set_updated_data(self._preserve_status(merged))

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
        self.async_set_updated_data(self._preserve_status(merged))

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
