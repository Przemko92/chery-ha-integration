from dataclasses import replace
from datetime import timedelta
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import CheryEuropeApi
from .const import DOMAIN
from .data import CheryData, merge_chery_data, vehicle_display_name
from .exceptions import CheryEuropeAuthError

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
                realtime = await self.api.get_vehicle_status(vin)
            except Exception as exc:
                _LOGGER.debug(
                    "Vehicle realtime unavailable for %s; using list data only: %s",
                    vin,
                    exc,
                )
                self._sync_vehicle_identity(base)
                return base
            if not realtime:
                self._sync_vehicle_identity(base)
                return base
            merged = merge_chery_data(
                base,
                CheryData.from_realtime(realtime, vin=vin),
            )
            self._sync_vehicle_identity(merged)
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

    def schedule_refresh_after_command(self) -> None:
        """Schedule post-command refreshes without failing the caller."""
        self.hass.async_create_task(self._refresh_after_command_safe())

    async def _refresh_after_command_safe(self) -> None:
        for delay in (0, 5, 10, 20):
            if delay:
                await asyncio.sleep(delay)
            try:
                await self.async_request_refresh()
            except Exception as exc:
                _LOGGER.debug("Post-command refresh failed: %s", exc)
