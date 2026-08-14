from dataclasses import replace
from datetime import timedelta
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import CheryEuropeApi
from .const import (
    CHARGING_POLL_INTERVAL,
    DEFAULT_MQTT_HOST,
    DEFAULT_MQTT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    DRIVE_WATCH_INTERVAL,
    HV_POLL_INTERVAL,
)
from .data import CheryData, apply_location, is_command_ack, merge_chery_data, vehicle_display_name
from .exceptions import CheryEuropeAuthError
from .mqtt import CheryEuropeMqttClient

_LOGGER = logging.getLogger(__name__)


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
        self._location_refresh_task = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
            update_method=self._async_update_data,
        )

    async def _async_update_data(self) -> CheryData:
        """Fetch the latest data from Chery Europe."""
        try:
            vehicles = await self.api.get_vehicle_list()
            if not vehicles:
                return CheryData()
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
                return data
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
                return base
            if not realtime:
                self._sync_vehicle_identity(base)
                self._apply_scan_interval(base)
                return await self._merge_location(base)
            merged = merge_chery_data(
                base,
                CheryData.from_realtime(realtime, vin=vin),
            )
            merged = await self._merge_location(merged)
            self._sync_vehicle_identity(merged)
            self._apply_scan_interval(merged)
            return merged
        except CheryEuropeAuthError as exc:
            raise ConfigEntryAuthFailed("Chery Europe authentication failed") from exc
        except Exception as exc:
            _LOGGER.exception("Chery Europe data update failed")
            raise UpdateFailed("Failed to update Chery Europe data") from exc

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

    def _apply_scan_interval(self, data: CheryData) -> None:
        """Poll faster while the vehicle is charging or the HV system is on."""
        if not self.poll_enabled:
            self.update_interval = None
            return
        if data.charge_gun_connected or data.is_charging:
            self.update_interval = CHARGING_POLL_INTERVAL
        elif data.hv_high_voltage_on or data.engine_on:
            self.update_interval = HV_POLL_INTERVAL
        else:
            self.update_interval = DEFAULT_SCAN_INTERVAL

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
                    self.async_set_updated_data(updated)
                return

    async def _refresh_after_command_safe(self) -> None:
        for delay in (0, 5, 10, 20):
            if delay:
                await asyncio.sleep(delay)
            try:
                await self.async_request_refresh()
            except Exception as exc:
                _LOGGER.debug("Post-command refresh failed: %s", exc)

    async def async_start_live_updates(self) -> None:
        """Start MQTT push and a lightweight drive-watch poller."""
        await self.hass.async_add_executor_job(self._start_mqtt)
        if self._watch_unsub is None:
            self._watch_unsub = async_track_time_interval(
                self.hass,
                self._async_drive_watch,
                DRIVE_WATCH_INTERVAL,
            )

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
            self.async_set_updated_data(located)
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
        self.async_set_updated_data(merged)

    async def _async_drive_watch(self, _now) -> None:
        """Cheap realtime check while parked so a trip or charge is noticed quickly."""
        if not self.poll_enabled or self.data is None or not self.data.vin:
            return
        if self.update_interval in {HV_POLL_INTERVAL, CHARGING_POLL_INTERVAL}:
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
        self.async_set_updated_data(merged)

    async def async_stop_live_updates(self) -> None:
        """Stop MQTT and the drive-watch timer."""
        if self._watch_unsub is not None:
            self._watch_unsub()
            self._watch_unsub = None
        mqtt = self._mqtt
        self._mqtt = None
        if mqtt is not None:
            await self.hass.async_add_executor_job(mqtt.stop)
