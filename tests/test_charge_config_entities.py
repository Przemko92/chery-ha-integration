# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Tests for charge schedule config entities syncing from the vehicle."""

from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.number import CheryEuropeChargeDurationNumber
from custom_components.chery_europe.time import CheryEuropeChargeStartTime

VIN = "VIN123456"


def _coordinator(data: CheryData | None = None):
    return SimpleNamespace(
        data=data or CheryData(vin=VIN),
        last_update_success=True,
        charge_start_minutes=480,
        charge_duration_hours=6,
        api=SimpleNamespace(send_command=AsyncMock(return_value={"ok": True})),
        async_set_updated_data=Mock(),
        schedule_refresh_after_command=Mock(),
    )


def _entry():
    return SimpleNamespace(entry_id="entry-1", options={"pin": "1234"})


def _vehicle_plan(*, start: int = 1320, duration_min: int = 480) -> CheryData:
    return CheryData(
        vin=VIN,
        scheduled_charge_enabled=True,
        charge_appoint_plan={
            "startTime": start,
            "timeConsuming": duration_min,
            "switchStatus": "1",
            "cycleData": [1, 2, 3, 4, 5, 6, 7],
        },
    )


def test_start_time_seeds_from_vehicle_plan():
    entity = CheryEuropeChargeStartTime(_coordinator(_vehicle_plan()), _entry())
    assert entity.native_value == time(22, 0)
    assert entity.coordinator.charge_start_minutes == 1320


def test_duration_seeds_from_vehicle_plan():
    entity = CheryEuropeChargeDurationNumber(_coordinator(_vehicle_plan()), _entry())
    assert entity.native_value == 8.0
    assert entity.coordinator.charge_duration_hours == 8


def test_start_time_follows_vehicle_updates_until_user_edits():
    coordinator = _coordinator(_vehicle_plan(start=1320))
    entity = CheryEuropeChargeStartTime(coordinator, _entry())
    entity.async_write_ha_state = lambda: None

    coordinator.data = _vehicle_plan(start=1380)  # 23:00
    entity._handle_coordinator_update()
    assert entity.native_value == time(23, 0)
    assert coordinator.charge_start_minutes == 1380


@pytest.mark.asyncio
async def test_user_edit_sends_plan_and_follows_later_vehicle_updates():
    coordinator = _coordinator(_vehicle_plan(start=1320, duration_min=480))
    start = CheryEuropeChargeStartTime(coordinator, _entry())
    duration = CheryEuropeChargeDurationNumber(coordinator, _entry())
    start.async_write_ha_state = lambda: None
    duration.async_write_ha_state = lambda: None

    await start.async_set_value(time(21, 30))
    await duration.async_set_native_value(7)

    start_call = coordinator.api.send_command.await_args_list[0]
    assert start_call.args[1] == "ve_1202"
    assert start_call.kwargs["start_minutes"] == 21 * 60 + 30
    assert start_call.kwargs["duration_hours"] == 8
    assert start_call.kwargs["enabled"] is True
    duration_call = coordinator.api.send_command.await_args_list[1]
    assert duration_call.kwargs["duration_hours"] == 7
    assert duration_call.kwargs["start_minutes"] == 21 * 60 + 30

    coordinator.data = _vehicle_plan(start=1380, duration_min=360)
    start._handle_coordinator_update()
    duration._handle_coordinator_update()
    assert start.native_value == time(23, 0)
    assert duration.native_value == 6.0
