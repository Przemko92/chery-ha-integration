# pyright: reportArgumentType=false, reportOptionalMemberAccess=false, reportOptionalSubscript=false
"""Tests for the departure time entity and the departure switch."""

from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.prepare_plan import (
    DEFAULT_DEPARTURE_TIME,
    DEPARTURE_PLAN_NAME,
    build_plan,
    find_plan_by_name,
)
from custom_components.chery_europe.switch import CheryEuropeDepartureSwitch
from custom_components.chery_europe.time import CheryEuropeDepartureTime

VIN = "VIN123456"


def _coordinator(plans=None, *, draft=None):
    data = CheryData(vin=VIN, prepare_plans=plans)
    return SimpleNamespace(
        data=data,
        last_update_success=True,
        departure_draft=draft,
        permissions={},
        _permissions_loaded=False,
        api=SimpleNamespace(
            send_travel_appointment=AsyncMock(return_value={"ok": True})
        ),
        invalidate_prepare_cache=Mock(),
        async_set_updated_data=Mock(),
        schedule_refresh_after_command=Mock(),
    )


def _entry():
    return SimpleNamespace(entry_id="entry-1", options={"pin": "1234"})


def _departure_plan(travel_time="07:30", *, enabled=True) -> dict:
    plan = build_plan(
        name=DEPARTURE_PLAN_NAME, travel_time=travel_time, enabled=enabled
    )
    plan["plan_id"] = "plan-1"
    return plan


def test_departure_time_falls_back_to_the_default_when_no_plan_is_stored() -> None:
    entity = CheryEuropeDepartureTime(_coordinator([]), _entry())
    assert entity.native_value == time(7, 30)
    assert DEFAULT_DEPARTURE_TIME == "07:30"


def test_departure_time_reads_the_plan_the_car_reports() -> None:
    entity = CheryEuropeDepartureTime(
        _coordinator([_departure_plan("06:05")]), _entry()
    )
    assert entity.native_value == time(6, 5)


def test_departure_time_follows_the_vehicle_after_a_poll() -> None:
    coordinator = _coordinator([_departure_plan("06:05")])
    entity = CheryEuropeDepartureTime(coordinator, _entry())
    entity.async_write_ha_state = lambda: None

    coordinator.data = CheryData(
        vin=VIN, prepare_plans=[_departure_plan("05:40")]
    )
    entity._handle_coordinator_update()

    assert entity.native_value == time(5, 40)


def test_switch_is_on_only_when_the_plan_is_armed() -> None:
    armed = CheryEuropeDepartureSwitch(
        _coordinator([_departure_plan(enabled=True)]), _entry()
    )
    disarmed = CheryEuropeDepartureSwitch(
        _coordinator([_departure_plan(enabled=False)]), _entry()
    )
    missing = CheryEuropeDepartureSwitch(_coordinator([]), _entry())

    assert armed.is_on is True
    assert disarmed.is_on is False
    assert missing.is_on is False


@pytest.mark.asyncio
async def test_setting_the_time_without_a_plan_only_keeps_a_draft() -> None:
    coordinator = _coordinator([])
    entity = CheryEuropeDepartureTime(coordinator, _entry())
    entity.async_write_ha_state = lambda: None

    await entity.async_set_value(time(6, 15))

    assert coordinator.departure_draft == "06:15"
    assert entity.native_value == time(6, 15)
    coordinator.api.send_travel_appointment.assert_not_awaited()


@pytest.mark.asyncio
async def test_turning_the_switch_on_creates_the_plan_from_the_draft() -> None:
    coordinator = _coordinator([], draft="06:15")
    entity = CheryEuropeDepartureSwitch(coordinator, _entry())
    entity.async_write_ha_state = lambda: None

    await entity.async_turn_on()

    vin, pin, plans, _permissions = coordinator.api.send_travel_appointment.await_args.args
    assert vin == VIN
    assert pin == "1234"
    departure = find_plan_by_name(plans)
    assert departure["travel_time"] == "06:15"
    assert departure["enabled"] is True
    updated_data = coordinator.async_set_updated_data.call_args.args[0]
    assert updated_data.prepare_plans == plans
    coordinator.invalidate_prepare_cache.assert_called_once()
    coordinator.schedule_refresh_after_command.assert_called_once()


@pytest.mark.asyncio
async def test_moving_the_time_keeps_the_other_plans_on_the_car() -> None:
    other = build_plan(name="Praca", travel_time="18:00")
    other["plan_id"] = "plan-2"
    coordinator = _coordinator([_departure_plan("07:30"), other])
    entity = CheryEuropeDepartureTime(coordinator, _entry())
    entity.async_write_ha_state = lambda: None

    await entity.async_set_value(time(7, 45))

    plans = coordinator.api.send_travel_appointment.await_args.args[2]
    departure = find_plan_by_name(plans)
    assert departure["plan_id"] == "plan-1"
    assert departure["travel_time"] == "07:45"
    assert find_plan_by_name(plans, "Praca")["travel_time"] == "18:00"


@pytest.mark.asyncio
async def test_turning_the_switch_off_disables_without_dropping_the_plan() -> None:
    coordinator = _coordinator([_departure_plan("07:30")])
    entity = CheryEuropeDepartureSwitch(coordinator, _entry())
    entity.async_write_ha_state = lambda: None

    await entity.async_turn_off()

    plans = coordinator.api.send_travel_appointment.await_args.args[2]
    departure = find_plan_by_name(plans)
    assert departure["enabled"] is False
    assert departure["plan_id"] == "plan-1"


@pytest.mark.asyncio
async def test_unknown_plan_list_blocks_the_write() -> None:
    coordinator = _coordinator(None)
    entity = CheryEuropeDepartureSwitch(coordinator, _entry())
    entity.async_write_ha_state = lambda: None

    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()

    coordinator.api.send_travel_appointment.assert_not_awaited()
