# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""GPS locate: MQTT 1301 vs command ACK, plus queryVehicleLocation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.command_exec import async_send_vehicle_command
from custom_components.chery_europe.coordinator import CheryEuropeDataUpdateCoordinator
from custom_components.chery_europe.data import (
    CheryData,
    apply_location,
    is_command_ack,
)
from custom_components.chery_europe.mqtt import parse_vehicle_mqtt_message

VIN = "LNNBDDEH5SG089258"
ACK = {
    "resultTime": "1786708073269",
    "hasAsy": "0",
    "result": "2",
    "seq": f"{VIN}-1786708056079",
}


def _coordinator(api=None):
    hass = Mock()
    hass.config_entries = Mock(async_update_entry=Mock())

    def _create_task(coro):
        if hasattr(coro, "close"):
            coro.close()
        return Mock()

    hass.async_create_task = Mock(side_effect=_create_task)
    entry = SimpleNamespace(options={}, title="Chery Europe")
    with patch(
        "custom_components.chery_europe.coordinator.DataUpdateCoordinator.__init__",
        return_value=None,
    ):
        coordinator = CheryEuropeDataUpdateCoordinator(
            hass, api or SimpleNamespace(), entry, None
        )
    coordinator.hass = hass
    coordinator.async_set_updated_data = Mock()
    coordinator.data = CheryData(vin=VIN)
    return coordinator


def test_parse_mqtt_1301_envelope():
    service, data = parse_vehicle_mqtt_message(
        {"content": {"serviceType": "1301", "data": {"lat": "50.06", "lon": "19.93"}}}
    )
    assert service == "1301"
    assert data["lat"] == "50.06"
    assert data["lon"] == "19.93"


def test_parse_mqtt_fills_geo_from_content_when_data_empty():
    service, data = parse_vehicle_mqtt_message(
        {"content": {"serviceType": "1301", "lat": "50.06", "lon": "19.93"}}
    )
    assert service == "1301"
    assert data["lat"] == "50.06"
    assert data["lon"] == "19.93"


def test_command_ack_without_coordinates_is_detected():
    assert is_command_ack(ACK) is True
    assert is_command_ack({"lat": "50", "lon": "19", "result": "2"}) is False


def test_mqtt_ack_does_not_overwrite_telemetry():
    coordinator = _coordinator()
    coordinator.data = CheryData(vin=VIN, battery_level=80, latitude=50.0, longitude=20.0)
    coordinator._apply_mqtt_payload("1209", ACK)
    coordinator.async_set_updated_data.assert_not_called()


def test_mqtt_1301_updates_device_tracker_coordinates():
    coordinator = _coordinator()
    coordinator._apply_mqtt_payload(
        "1301",
        {
            "lat": "50.0614",
            "lon": "19.9372",
            "direction": "180",
            "gpsTime": "1786708073269",
        },
    )
    updated = coordinator.async_set_updated_data.call_args[0][0]
    assert updated.latitude == pytest.approx(50.0614)
    assert updated.longitude == pytest.approx(19.9372)
    assert updated.gps_direction == 180
    assert updated.gps_time is not None


def test_mqtt_1301_without_coords_schedules_rest_query():
    coordinator = _coordinator()
    coordinator._apply_mqtt_payload("1301", ACK)
    coordinator.hass.async_create_task.assert_called_once()


def test_apply_location_requires_both_coordinates():
    data = CheryData(vin=VIN)
    assert apply_location(data, ACK) is data
    updated = apply_location(data, {"lat": "50.1", "lon": "19.9"})
    assert updated.latitude == pytest.approx(50.1)
    assert updated.longitude == pytest.approx(19.9)


@pytest.mark.asyncio
async def test_locate_command_schedules_location_refresh():
    coordinator = _coordinator(
        SimpleNamespace(send_command=AsyncMock(return_value={"ok": True}))
    )
    coordinator.schedule_refresh_after_command = Mock()
    coordinator.schedule_location_refresh = Mock()
    entry = SimpleNamespace(options={"pin": "1234"})

    await async_send_vehicle_command(
        coordinator, entry, VIN, {}, command_id="ve_1209"
    )

    coordinator.schedule_location_refresh.assert_called_once()
    coordinator.schedule_refresh_after_command.assert_called_once()


@pytest.mark.asyncio
async def test_refresh_location_applies_rest_payload():
    api = SimpleNamespace(
        get_vehicle_location=AsyncMock(return_value={"lat": "50.06", "lon": "19.93"})
    )
    coordinator = _coordinator(api)
    coordinator.data = CheryData(vin=VIN)

    with patch("custom_components.chery_europe.coordinator.asyncio.sleep", new=AsyncMock()):
        await coordinator._async_refresh_location()

    updated = coordinator.async_set_updated_data.call_args[0][0]
    assert updated.latitude == pytest.approx(50.06)
    assert updated.longitude == pytest.approx(19.93)
