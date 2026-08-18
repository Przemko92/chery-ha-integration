# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Tests for operational buttons, polling options and restore sensors."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.const import (
    CONF_POLL_CHARGING,
    CONF_POLL_HV,
    CONF_POLL_NORMAL,
    DEFAULT_POLL_CHARGING_MIN,
    DEFAULT_POLL_HV_MIN,
    DEFAULT_POLL_NORMAL_MIN,
)
from custom_components.chery_europe.coordinator import CheryEuropeDataUpdateCoordinator
from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.sensor import CheryEuropeSensor, STATUS_SENSOR_DESCRIPTIONS

VIN = "VIN123"


def _coordinator(api=None, options=None):
    hass = Mock()
    hass.config_entries = Mock(async_update_entry=Mock())
    hass.async_create_task = Mock()
    entry = SimpleNamespace(options=options or {}, title="Chery Europe")
    with patch(
        "custom_components.chery_europe.coordinator.DataUpdateCoordinator.__init__",
        return_value=None,
    ):
        coordinator = CheryEuropeDataUpdateCoordinator(
            hass, api or SimpleNamespace(), entry, None
        )
    coordinator.hass = hass
    coordinator.async_set_updated_data = Mock(
        side_effect=lambda data: setattr(coordinator, "data", data) or data
    )
    coordinator.data = CheryData(vin=VIN)
    return coordinator


def test_poll_interval_uses_options():
    coordinator = _coordinator(
        options={
            CONF_POLL_NORMAL: 30,
            CONF_POLL_CHARGING: 5,
            CONF_POLL_HV: 3,
        }
    )
    parked = CheryData(vin=VIN)
    charging = CheryData(vin=VIN, is_charging=True)
    hv = CheryData(vin=VIN, hv_high_voltage_on=True)

    assert coordinator._poll_interval_for(parked) == timedelta(minutes=30)
    assert coordinator._poll_interval_for(charging) == timedelta(minutes=5)
    assert coordinator._poll_interval_for(hv) == timedelta(minutes=3)


def test_poll_interval_zero_disables_polling():
    coordinator = _coordinator(options={CONF_POLL_NORMAL: 0})
    assert coordinator._poll_interval_for(CheryData(vin=VIN)) is None


def test_update_poll_options_reads_defaults():
    coordinator = _coordinator()
    coordinator.update_poll_options({})
    assert coordinator.poll_normal_min == DEFAULT_POLL_NORMAL_MIN
    assert coordinator.poll_charging_min == DEFAULT_POLL_CHARGING_MIN
    assert coordinator.poll_hv_min == DEFAULT_POLL_HV_MIN


@pytest.mark.asyncio
async def test_async_wake_updates_wake_status():
    api = SimpleNamespace(send_command=AsyncMock(return_value={"ok": True}))
    coordinator = _coordinator(api)
    coordinator.schedule_location_refresh = Mock()
    coordinator.schedule_refresh_after_command = Mock()
    entry = coordinator.entry
    entry.options = {"pin": "1234"}

    await coordinator.async_wake()

    api.send_command.assert_awaited_once_with(VIN, "ve_1209", "1234")
    updated = coordinator.async_set_updated_data.call_args[0][0]
    assert "✅" in (updated.wake_status or "")


@pytest.mark.asyncio
async def test_async_probe_reads_location_without_command():
    api = SimpleNamespace(
        send_command=AsyncMock(return_value={"ok": True}),
        get_vehicle_location=AsyncMock(return_value={"lat": "50.1", "lon": "19.9"}),
    )
    coordinator = _coordinator(api)

    await coordinator.async_probe()

    api.send_command.assert_not_awaited()
    updated = coordinator.async_set_updated_data.call_args[0][0]
    assert updated.latitude == pytest.approx(50.1)


def test_restore_sensor_keeps_last_known_value():
    from custom_components.chery_europe.sensor import SENSOR_DESCRIPTIONS

    coordinator = _coordinator()
    coordinator.data = CheryData(vin=VIN, battery_level=70)
    sensor = CheryEuropeSensor(
        coordinator, SENSOR_DESCRIPTIONS[0], SimpleNamespace(entry_id="e1")
    )
    sensor._restored = 55
    coordinator.data = CheryData(vin=VIN, battery_level=None)
    assert sensor.native_value == 55


def test_preserve_control_state_when_realtime_is_missing():
    coordinator = _coordinator()
    coordinator.data = CheryData(
        vin=VIN,
        front_windshield_heating=True,
        rear_window_defrost=False,
        hvac_enabled=True,
        target_temperature=22,
        is_locked=True,
    )

    refreshed = coordinator._preserve_control_state(CheryData(vin=VIN, battery_level=70))

    assert refreshed.front_windshield_heating is True
    assert refreshed.rear_window_defrost is False
    assert refreshed.hvac_enabled is True
    assert refreshed.target_temperature == 22
    assert refreshed.is_locked is True
    assert refreshed.battery_level == 70


def test_status_sensor_descriptions_exist():
    keys = {desc.key for desc in STATUS_SENSOR_DESCRIPTIONS}
    assert keys == {"command_status", "wake_status", "probe_status"}
