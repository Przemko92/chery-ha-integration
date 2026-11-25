# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Tests for the charging end time derived from the start and the duration."""

from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.number import CheryEuropeChargeDurationNumber
from custom_components.chery_europe.time import (
    CheryEuropeChargeEndTime,
    CheryEuropeChargeStartTime,
)

VIN = "VIN123456"


def _coordinator(
    data: CheryData | None = None, *, start_minutes: int = 480, duration_hours: float = 6
):
    """Fake coordinator carrying the draft the start/duration entities keep."""
    coordinator = SimpleNamespace(
        data=data or CheryData(vin=VIN),
        last_update_success=True,
        charge_start_minutes=start_minutes,
        charge_duration_hours=duration_hours,
        charge_schedule_listeners=[],
        api=SimpleNamespace(send_command=AsyncMock(return_value={"ok": True})),
        async_set_updated_data=Mock(),
        schedule_refresh_after_command=Mock(),
    )
    coordinator.async_notify_charge_schedule = Mock()
    return coordinator


def _entry():
    return SimpleNamespace(entry_id="entry-1", options={"pin": "1234"})


def _plan(*, start: int = 1320, duration_min: int = 480) -> CheryData:
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


def _end_entity(coordinator):
    entity = CheryEuropeChargeEndTime(coordinator, _entry())
    entity.async_write_ha_state = lambda: None
    return entity


def test_end_wraps_into_the_next_day() -> None:
    """22:00 plus eight hours is 06:00 tomorrow, and the window says so."""
    coordinator = _coordinator(_plan(start=1320), start_minutes=1320, duration_hours=8)
    end = _end_entity(coordinator)

    assert end.native_value == time(6, 0)
    assert end.extra_state_attributes["start_time"] == "22:00"
    assert end.extra_state_attributes["end_time"] == "06:00"
    assert end.extra_state_attributes["next_day"] is True


def test_end_stays_inside_the_same_day() -> None:
    """08:00 plus six hours is 14:00 today."""
    coordinator = _coordinator(start_minutes=8 * 60)
    end = _end_entity(coordinator)

    assert end.native_value == time(14, 0)
    assert end.extra_state_attributes["next_day"] is False


@pytest.mark.asyncio
async def test_moving_the_end_shortens_the_duration() -> None:
    """An end of 04:00 for a 22:00 start is a six hour window."""
    coordinator = _coordinator(_plan(start=1320), start_minutes=1320, duration_hours=8)
    end = _end_entity(coordinator)

    await end.async_set_value(time(4, 0))

    call = coordinator.api.send_command.await_args
    assert call.args[1] == "ve_1202"
    assert call.kwargs["start_minutes"] == 22 * 60
    assert call.kwargs["duration_hours"] == 6
    assert call.kwargs["enabled"] is True
    assert coordinator.charge_duration_hours == 6


@pytest.mark.asyncio
async def test_an_end_before_the_start_lands_on_the_next_day() -> None:
    """An 08:00 start with an end of 06:00 is a 22 hour window."""
    coordinator = _coordinator()
    coordinator.charge_start_minutes = 8 * 60
    end = _end_entity(coordinator)

    await end.async_set_value(time(6, 0))

    assert coordinator.api.send_command.await_args.kwargs["duration_hours"] == 22
    assert end.native_value == time(6, 0)
    assert end.extra_state_attributes["next_day"] is True


@pytest.mark.asyncio
async def test_an_end_equal_to_the_start_is_a_full_day() -> None:
    """The same clock time on both sides means the whole 24 hours."""
    coordinator = _coordinator()
    coordinator.charge_start_minutes = 8 * 60
    end = _end_entity(coordinator)

    await end.async_set_value(time(8, 0))

    assert coordinator.api.send_command.await_args.kwargs["duration_hours"] == 24


@pytest.mark.asyncio
async def test_a_short_end_is_lifted_to_the_shortest_window() -> None:
    """The car takes a full hour at least, so 22:00 -> 22:30 goes out as 60 minutes."""
    coordinator = _coordinator(_plan(start=1320), start_minutes=1320, duration_hours=8)
    end = _end_entity(coordinator)

    await end.async_set_value(time(22, 30))

    assert coordinator.api.send_command.await_args.kwargs["duration_hours"] == 1.0
    assert end.native_value == time(23, 0)


@pytest.mark.asyncio
async def test_an_end_off_the_grid_is_snapped() -> None:
    """22:00 plus 7 h 10 min is snapped to the quarter hour the car accepts."""
    coordinator = _coordinator(_plan(start=1320), start_minutes=1320, duration_hours=8)
    end = _end_entity(coordinator)

    await end.async_set_value(time(5, 10))

    assert coordinator.api.send_command.await_args.kwargs["duration_hours"] == 7.25


@pytest.mark.asyncio
async def test_moving_the_start_keeps_the_end_and_shortens_the_duration() -> None:
    """A 22:00 start with 06:00 end becomes 8.5 h when the start moves to 21:30."""
    coordinator = _coordinator(_plan(start=1320), start_minutes=1320, duration_hours=8)
    start = CheryEuropeChargeStartTime(coordinator, _entry())
    end = _end_entity(coordinator)
    start.async_write_ha_state = lambda: None
    coordinator.charge_schedule_listeners.extend([start, end])

    await start.async_set_value(time(21, 30))

    assert coordinator.api.send_command.await_args.kwargs["duration_hours"] == 8.5
    assert end.native_value == time(6, 0)
    assert coordinator.async_notify_charge_schedule.called


@pytest.mark.asyncio
async def test_a_full_day_survives_a_start_change() -> None:
    """A 24 h window has no distinct end, so it stays 24 h."""
    coordinator = _coordinator(start_minutes=8 * 60, duration_hours=24)
    start = CheryEuropeChargeStartTime(coordinator, _entry())
    start.async_write_ha_state = lambda: None

    await start.async_set_value(time(9, 0))

    assert coordinator.api.send_command.await_args.kwargs["duration_hours"] == 24


@pytest.mark.asyncio
async def test_moving_the_duration_moves_the_end() -> None:
    """A shorter duration pulls the end back, keeping the start."""
    coordinator = _coordinator(_plan(start=1320), start_minutes=1320, duration_hours=8)
    duration = CheryEuropeChargeDurationNumber(coordinator, _entry())
    end = _end_entity(coordinator)
    duration.async_write_ha_state = lambda: None
    coordinator.charge_schedule_listeners.extend([duration, end])

    await duration.async_set_native_value(4)

    assert coordinator.api.send_command.await_args.kwargs["start_minutes"] == 22 * 60
    assert end.native_value == time(2, 0)
    assert end.extra_state_attributes["duration_hours"] == 4


def test_end_follows_the_duration_reported_by_the_car() -> None:
    """A refresh that changes the duration moves the end without a write."""
    coordinator = _coordinator(_plan(start=1320), start_minutes=1320, duration_hours=8)
    end = _end_entity(coordinator)
    end.async_write_ha_state = lambda: None

    coordinator.data = _plan(start=1320, duration_min=360)
    end._handle_coordinator_update()

    assert coordinator.charge_duration_hours == 6
    assert end.native_value == time(4, 0)
