# pyright: reportMissingImports=false
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.chery_europe.const import POST_COMMAND_REFRESH_DELAYS
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
        get_vehicle_location=AsyncMock(
            return_value={"lat": "50.06", "lon": "19.93"}
        ),
        get_vehicle_authority=AsyncMock(return_value={}),
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
    assert data.latitude == pytest.approx(50.06)
    assert data.longitude == pytest.approx(19.93)
    api.get_vehicle_status.assert_awaited_once_with("DEMO1234567890")
    api.get_vehicle_location.assert_awaited_once_with("DEMO1234567890")


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


@pytest.mark.asyncio
async def test_post_command_refresh_waits_before_first_poll():
    """Stale telemetry must not overwrite optimistic state immediately."""
    coordinator = _coordinator(SimpleNamespace())
    events: list[tuple[str, float | None]] = []

    async def sleep(delay):
        events.append(("sleep", delay))

    async def refresh():
        events.append(("refresh", None))

    coordinator.async_request_refresh = AsyncMock(side_effect=refresh)

    with patch("custom_components.chery_europe.coordinator.asyncio.sleep", sleep):
        await coordinator._refresh_after_command_safe()

    assert events[0] == ("sleep", 5)
    assert events == [
        item
        for delay in POST_COMMAND_REFRESH_DELAYS
        for item in (("sleep", delay), ("refresh", None))
    ]


@pytest.mark.asyncio
async def test_keepalive_refreshes_near_expiry_token():
    api = SimpleNamespace(ensure_fresh_token=AsyncMock(return_value=True))
    coordinator = _coordinator(api)

    await coordinator._async_keepalive(None)

    api.ensure_fresh_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_keepalive_auth_error_does_not_raise():
    api = SimpleNamespace(
        ensure_fresh_token=AsyncMock(side_effect=CheryEuropeAuthError("revoked"))
    )
    coordinator = _coordinator(api)

    await coordinator._async_keepalive(None)


@pytest.mark.asyncio
async def test_start_and_stop_keepalive_registers_timer():
    api = SimpleNamespace()
    coordinator = _coordinator(api)
    unsub = Mock()

    with patch(
        "custom_components.chery_europe.coordinator.async_track_time_interval",
        return_value=unsub,
    ) as track:
        coordinator.async_start_keepalive()
        coordinator.async_start_keepalive()  # idempotent

    track.assert_called_once()
    assert coordinator._keepalive_unsub is unsub

    await coordinator.async_stop_live_updates()
    unsub.assert_called_once()
    assert coordinator._keepalive_unsub is None
