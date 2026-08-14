# pyright: reportMissingImports=false
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.chery_europe.coordinator import CheryEuropeDataUpdateCoordinator
from custom_components.chery_europe.exceptions import CheryEuropeAuthError, CheryEuropeTimeoutError


DEMO_VEHICLE = {
    "vin": "DEMO1234567890",
    "fullName": "Tiggo 9 PHEV",
    "colorNameEn": "EXEED White",
    "carPicture": "https://example.com/car.png",
    "nickname": "Tiggo 9",
    "minTemperature": 16.0,
    "maxTemperature": 30.0,
}
DEMO_STATUS = {
    "dumpEnergy": "88",
    "pureElectricRange": "60",
    "mileageSurplus": "250",
    "averageFuel": "6.2",
}


def _coordinator(api):
    hass = Mock()
    hass.config_entries = Mock(async_update_entry=Mock())
    entry = SimpleNamespace(options={}, title="Chery Europe")
    with patch("custom_components.chery_europe.coordinator.DataUpdateCoordinator.__init__", return_value=None):
        coordinator = CheryEuropeDataUpdateCoordinator(hass, api, entry, timedelta(minutes=15))
    coordinator.hass = hass
    return coordinator


@pytest.mark.asyncio
async def test_coordinator_update_fetches_vehicle_status_for_first_vehicle():
    api = SimpleNamespace(
        get_vehicle_list=AsyncMock(return_value=[DEMO_VEHICLE]),
        get_vehicle_status=AsyncMock(return_value=DEMO_STATUS),
    )
    coordinator = _coordinator(api)
    device_registry = Mock(async_get_device=Mock(return_value=None))

    with patch("custom_components.chery_europe.coordinator.dr.async_get", return_value=device_registry):
        data = await coordinator._async_update_data()

    assert data.vin == "DEMO1234567890"
    assert data.battery_level == 88.0
    assert data.range_km == 310.0
    assert data.vehicle_full_name == "Tiggo 9 PHEV"
    assert data.vehicle_color_name_en == "EXEED White"
    assert data.average_fuel_consumption == 6.2
    assert data.min_temperature == 16.0
    assert data.max_temperature == 30.0
    api.get_vehicle_status.assert_awaited_once_with("DEMO1234567890")


@pytest.mark.asyncio
async def test_coordinator_timeout_raises_update_failed():
    api = SimpleNamespace(
        get_vehicle_list=AsyncMock(side_effect=CheryEuropeTimeoutError("timeout")),
        get_vehicle_status=AsyncMock(),
    )
    coordinator = _coordinator(api)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_auth_failure_requests_reauth():
    api = SimpleNamespace(
        get_vehicle_list=AsyncMock(side_effect=CheryEuropeAuthError("expired")),
        get_vehicle_status=AsyncMock(),
    )
    coordinator = _coordinator(api)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()
