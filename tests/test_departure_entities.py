# pyright: reportArgumentType=false, reportOptionalMemberAccess=false, reportOptionalSubscript=false
"""Tests for the departure time entity and the departure switch."""

from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.departure import async_set_departure
from custom_components.chery_europe.prepare_plan import (
    DEFAULT_DEPARTURE_TIME,
    DEPARTURE_PLAN_NAME,
    build_plan,
    find_plan_by_name,
)
from custom_components.chery_europe.button import CheryEuropeDepartureSoonButton
from custom_components.chery_europe.switch import CheryEuropeDepartureSwitch
from custom_components.chery_europe.time import CheryEuropeDepartureTime

VIN = "VIN123456"


@pytest.fixture(autouse=True)
def scheduled_restores(monkeypatch):
    """Collect the restore timers instead of scheduling them on a real loop."""
    from custom_components.chery_europe import departure as departure_module

    scheduled: list[tuple[float, object]] = []

    def _call_later(hass, delay, action):
        handle = Mock()
        scheduled.append((delay, action, handle))
        return handle

    monkeypatch.setattr(departure_module, "async_call_later", _call_later)
    return scheduled


def _coordinator(plans=None, *, draft=None, armed=None, days=None):
    data = CheryData(vin=VIN, prepare_plans=plans)
    return SimpleNamespace(
        data=data,
        last_update_success=True,
        departure_draft=draft,
        departure_armed=armed,
        departure_days=days,
        permissions={},
        _permissions_loaded=False,
        api=SimpleNamespace(
            send_travel_appointment=AsyncMock(return_value={"ok": True})
        ),
        invalidate_prepare_cache=Mock(),
        async_set_updated_data=Mock(),
        async_add_listener=Mock(return_value=Mock()),
        hass=SimpleNamespace(),
        schedule_refresh_after_command=Mock(),
    )


def _entry():
    return SimpleNamespace(entry_id="entry-1", options={"pin": "1234"})


def _departure_plan(travel_time="07:30", *, enabled=True, repeat="daily") -> dict:
    plan = build_plan(
        name=DEPARTURE_PLAN_NAME,
        travel_time=travel_time,
        enabled=enabled,
        repeat=repeat,
    )
    plan["plan_id"] = "plan-1"
    return plan


def test_departure_time_falls_back_to_the_default_when_no_plan_is_stored() -> None:
    entity = CheryEuropeDepartureTime(_coordinator([]), _entry())
    assert entity.native_value == time(6, 5)
    assert DEFAULT_DEPARTURE_TIME == "06:05"


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


def test_switch_follows_the_commanded_state_when_the_car_reports_no_plan() -> None:
    """The car cannot be read back, so the switch trusts what HA last commanded."""
    armed = CheryEuropeDepartureSwitch(_coordinator([], armed=True), _entry())
    assert armed.is_on is True

    idle = CheryEuropeDepartureSwitch(_coordinator([], armed=False), _entry())
    assert idle.is_on is False


@pytest.mark.asyncio
async def test_arming_keeps_the_stored_weekdays() -> None:
    """A plan created from scratch repeats on the stored days, not every day."""
    coordinator = _coordinator([], draft="06:05", armed=False, days=[1, 2, 3, 4, 5])

    await async_set_departure(coordinator, _entry(), enabled=True)

    plans = coordinator.api.send_travel_appointment.await_args.args[2]
    plan = find_plan_by_name(plans, DEPARTURE_PLAN_NAME)
    assert plan is not None
    assert plan["travel_time"] == "06:05"
    assert plan["days"] == [1, 2, 3, 4, 5]
    assert plan["enabled"] is True
    assert coordinator.departure_armed is True


@pytest.mark.asyncio
async def test_weekday_switch_adds_a_day_and_writes_the_plan(monkeypatch):
    from custom_components.chery_europe import departure as departure_module
    from custom_components.chery_europe.switch import (
        DEPARTURE_DAY_DESCRIPTIONS,
        CheryEuropeDepartureDaySwitch,
    )

    coordinator = _coordinator(draft="06:05", armed=True, days=[1, 3, 4, 5])
    entry = SimpleNamespace(entry_id="entry-1", runtime_data=coordinator)
    writes: list[list[int]] = []

    async def _fake_set(coord, ent):
        writes.append(list(coord.departure_days))

    monkeypatch.setattr(departure_module, "async_set_departure", _fake_set)

    entity = CheryEuropeDepartureDaySwitch(
        coordinator, DEPARTURE_DAY_DESCRIPTIONS[1][1], entry, 2
    )
    assert entity.is_on is False
    entity.async_write_ha_state = lambda: None

    await entity.async_turn_on()

    assert coordinator.departure_days == [1, 2, 3, 4, 5]
    assert writes == [[1, 2, 3, 4, 5]]


@pytest.mark.asyncio
async def test_weekday_switch_refuses_to_drop_the_last_day(monkeypatch):
    from custom_components.chery_europe import departure as departure_module
    from custom_components.chery_europe.switch import (
        DEPARTURE_DAY_DESCRIPTIONS,
        CheryEuropeDepartureDaySwitch,
    )

    coordinator = _coordinator(draft="06:05", armed=True, days=[6])
    entry = SimpleNamespace(entry_id="entry-1", runtime_data=coordinator)
    writes: list[list[int]] = []

    async def _fake_set(coord, ent):
        writes.append(list(coord.departure_days))

    monkeypatch.setattr(departure_module, "async_set_departure", _fake_set)

    entity = CheryEuropeDepartureDaySwitch(
        coordinator, DEPARTURE_DAY_DESCRIPTIONS[5][1], entry, 6
    )
    assert entity.is_on is True
    entity.async_write_ha_state = lambda: None

    with pytest.raises(HomeAssistantError):
        await entity.async_turn_off()

    assert coordinator.departure_days == [6]
    assert writes == []


def _restored(state: str, attributes: dict | None = None):
    return SimpleNamespace(state=state, attributes=attributes or {})


@pytest.mark.asyncio
async def test_a_legacy_off_state_is_not_believed_and_the_plan_reads_armed(monkeypatch):
    """A restored off that HA never commanded is a leftover default, not a command."""
    from homeassistant.helpers.update_coordinator import CoordinatorEntity

    from custom_components.chery_europe.switch import CheryEuropeDepartureSwitch

    monkeypatch.setattr(CoordinatorEntity, "async_added_to_hass", AsyncMock())
    coordinator = _coordinator([])
    entity = CheryEuropeDepartureSwitch(coordinator, _entry())
    entity.async_write_ha_state = lambda: None
    entity.async_get_last_state = AsyncMock(return_value=_restored("off"))

    await entity.async_added_to_hass()

    assert coordinator.departure_armed is True
    assert entity.is_on is True
    assert entity.extra_state_attributes is None


@pytest.mark.asyncio
async def test_a_commanded_off_state_survives_a_reload(monkeypatch):
    """Disarming from HA is remembered across restarts."""
    from homeassistant.helpers.update_coordinator import CoordinatorEntity

    from custom_components.chery_europe.switch import CheryEuropeDepartureSwitch

    monkeypatch.setattr(CoordinatorEntity, "async_added_to_hass", AsyncMock())
    coordinator = _coordinator([])
    entity = CheryEuropeDepartureSwitch(coordinator, _entry())
    entity.async_write_ha_state = lambda: None
    entity.async_get_last_state = AsyncMock(
        return_value=_restored("off", {"armed_commanded": True})
    )

    await entity.async_added_to_hass()

    assert coordinator.departure_armed is False
    assert entity.is_on is False
    assert entity.extra_state_attributes == {"armed_commanded": True}

# --- quick "departure in 15 minutes" button ---------------------------------

def test_soon_button_target_rounds_down_and_keeps_the_press_weekday() -> None:
    """The target time is now +15 minutes, with the weekday of the press."""
    from datetime import datetime

    from custom_components.chery_europe.button import departure_soon_target

    travel_time, days = departure_soon_target(datetime(2026, 11, 25, 6, 0, 42))
    assert travel_time == "06:15"
    assert days == [3]  # Wednesday


def test_soon_button_target_wraps_past_midnight() -> None:
    """A press late at night schedules tomorrow's clock time today."""
    from datetime import datetime

    from custom_components.chery_europe.button import departure_soon_target

    travel_time, days = departure_soon_target(datetime(2026, 11, 25, 23, 50))
    assert travel_time == "00:05"
    assert days == [3]


@pytest.mark.asyncio
async def test_soon_button_shifts_the_time_arms_the_plan_and_adds_today(
    monkeypatch,
) -> None:
    """One press rewrites the plan: +15 minutes, on, and today enabled."""
    from datetime import datetime

    from custom_components.chery_europe import button as button_module

    coordinator = _coordinator(
        [_departure_plan("06:05", repeat="workdays")],
        draft="06:05",
        armed=False,
        days=[1, 2, 3],
    )
    entity = button_module.CheryEuropeDepartureSoonButton(coordinator, _entry())
    monkeypatch.setattr(
        button_module,
        "dt_util",
        SimpleNamespace(now=lambda: datetime(2026, 11, 28, 6, 0)),  # Saturday
    )

    await entity.async_press()

    sent = coordinator.api.send_travel_appointment.await_args.args[2]
    plan = find_plan_by_name(sent, DEPARTURE_PLAN_NAME)
    assert plan is not None
    assert plan["travel_time"] == "06:15"
    assert plan["enabled"] is True
    # The plan already repeated on the workdays; Saturday joins them.
    assert plan["days"] == [1, 2, 3, 4, 5, 6]
    assert coordinator.departure_draft == "06:15"
    assert coordinator.departure_armed is True
    assert coordinator.departure_days == [1, 2, 3, 4, 5, 6]


@pytest.mark.asyncio
async def test_soon_button_leaves_every_departure_entity_switched_on(
    monkeypatch,
) -> None:
    """After the press the plan is armed, today is on and the time is +15."""
    from datetime import datetime

    from custom_components.chery_europe import button as button_module
    from custom_components.chery_europe.switch import (
        DEPARTURE_DAY_DESCRIPTIONS,
        CheryEuropeDepartureDaySwitch,
    )

    coordinator = _coordinator(
        [_departure_plan("06:05", repeat="workdays")], draft="06:05", armed=False
    )
    monkeypatch.setattr(
        button_module,
        "dt_util",
        SimpleNamespace(now=lambda: datetime(2026, 11, 28, 8, 7)),  # Saturday
    )
    # A real coordinator publishes the written plan back to every entity.
    coordinator.async_set_updated_data = lambda data: setattr(
        coordinator, "data", data
    )

    await button_module.CheryEuropeDepartureSoonButton(
        coordinator, _entry()
    ).async_press()

    day_switches = {
        day: CheryEuropeDepartureDaySwitch(
            coordinator,
            dict(DEPARTURE_DAY_DESCRIPTIONS)[day],
            _entry(),
            day,
        )
        for day in range(1, 8)
    }
    assert CheryEuropeDepartureSwitch(coordinator, _entry()).is_on is True
    assert CheryEuropeDepartureTime(coordinator, _entry()).native_value == time(8, 22)
    assert day_switches[6].is_on is True
    assert day_switches[3].is_on is True  # Wednesday keeps its weekday


@pytest.mark.asyncio
async def test_soon_button_does_not_drop_existing_days(monkeypatch) -> None:
    """Days already on the plan survive the press."""
    from datetime import datetime

    from custom_components.chery_europe import button as button_module

    coordinator = _coordinator([], draft="07:00", armed=False, days=[7])
    entity = button_module.CheryEuropeDepartureSoonButton(coordinator, _entry())
    monkeypatch.setattr(
        button_module,
        "dt_util",
        SimpleNamespace(now=lambda: datetime(2026, 11, 25, 12, 30)),  # Wednesday
    )

    await entity.async_press()

    sent = coordinator.api.send_travel_appointment.await_args.args[2]
    assert find_plan_by_name(sent, DEPARTURE_PLAN_NAME)["days"] == [3, 7]


@pytest.mark.asyncio
async def test_soon_button_fails_closed_when_the_plans_are_unknown() -> None:
    """Without the plan list the button refuses instead of wiping other plans."""
    coordinator = _coordinator(None, draft="06:05", armed=False, days=[1])
    entity = CheryEuropeDepartureSoonButton(coordinator, _entry())

    with pytest.raises(HomeAssistantError):
        await entity.async_press()

    assert coordinator.departure_days == [1]
    coordinator.api.send_travel_appointment.assert_not_awaited()


@pytest.mark.asyncio
async def test_soon_button_remembers_the_parameters_of_the_first_press(
    monkeypatch,
) -> None:
    """A second press shifts the clock again but keeps the original snapshot."""
    from datetime import datetime

    from custom_components.chery_europe import button as button_module

    coordinator = _coordinator(
        [_departure_plan("07:30", repeat="workdays")], draft="07:30", armed=True
    )
    monkeypatch.setattr(
        button_module,
        "dt_util",
        SimpleNamespace(now=lambda: datetime(2026, 11, 25, 6, 0)),  # Wednesday
    )
    entity = button_module.CheryEuropeDepartureSoonButton(coordinator, _entry())

    await entity.async_press()
    first = dict(coordinator.departure_previous)
    await entity.async_press()

    assert first == {
        "travel_time": "07:30",
        "days": [1, 2, 3, 4, 5],
        "enabled": True,
    }
    assert coordinator.departure_previous == first
    assert coordinator.departure_draft == "06:15"


def _freeze(monkeypatch, *, now, utcnow):
    """Point both modules at the same frozen clock."""
    from datetime import datetime

    from custom_components.chery_europe import button as button_module
    from custom_components.chery_europe import departure as departure_module

    fake = SimpleNamespace(
        now=lambda: now,
        utcnow=lambda: utcnow,
        parse_datetime=lambda value: datetime.fromisoformat(value),
    )
    monkeypatch.setattr(button_module, "dt_util", fake)
    monkeypatch.setattr(departure_module, "dt_util", fake)


@pytest.fixture
def soon_button():
    """Build the quick departure entity against a plan the owner already had."""
    from custom_components.chery_europe import button as button_module

    coordinator = _coordinator(
        [_departure_plan("07:30", repeat="workdays")], draft="07:30", armed=True
    )
    return button_module.CheryEuropeDepartureSoonButton(coordinator, _entry()), coordinator


@pytest.mark.asyncio
async def test_soon_button_arms_the_automatic_restore(
    soon_button, scheduled_restores, monkeypatch
) -> None:
    """Pressing the button schedules the restore and keeps the first snapshot."""
    from datetime import datetime

    entity, coordinator = soon_button
    _freeze(
        monkeypatch,
        now=datetime(2026, 11, 25, 6, 0),
        utcnow=datetime(2026, 11, 25, 5, 0),
    )

    await entity.async_press()

    assert scheduled_restores[0][0] == 15 * 60
    assert coordinator.departure_previous == {
        "travel_time": "07:30",
        "days": [1, 2, 3, 4, 5],
        "enabled": True,
    }
    assert coordinator.departure_restore_at == datetime(2026, 11, 25, 5, 15)
    assert entity.extra_state_attributes["departure_restore_at"] == "2026-11-25T05:15:00"


@pytest.mark.asyncio
async def test_a_second_press_restarts_the_clock_but_keeps_the_first_snapshot(
    soon_button, scheduled_restores, monkeypatch
) -> None:
    """Pressing again moves the deadline out without losing the original plan."""
    from datetime import datetime

    entity, coordinator = soon_button
    _freeze(
        monkeypatch,
        now=datetime(2026, 11, 25, 6, 0),
        utcnow=datetime(2026, 11, 25, 5, 0),
    )
    await entity.async_press()
    first = dict(coordinator.departure_previous)

    await entity.async_press()

    assert coordinator.departure_previous == first
    assert len(scheduled_restores) == 2
    assert scheduled_restores[0][2].called is True


@pytest.mark.asyncio
async def test_automatic_restore_puts_the_previous_departure_back(
    soon_button, scheduled_restores, monkeypatch
) -> None:
    """Fifteen minutes later the old time, weekdays and arming are written back."""
    from datetime import datetime

    entity, coordinator = soon_button
    _freeze(
        monkeypatch,
        now=datetime(2026, 11, 25, 6, 0),
        utcnow=datetime(2026, 11, 25, 5, 0),
    )
    await entity.async_press()

    await scheduled_restores[0][1](None)

    sent = coordinator.api.send_travel_appointment.await_args.args[2]
    plan = find_plan_by_name(sent, DEPARTURE_PLAN_NAME)
    assert plan["travel_time"] == "07:30"
    assert plan["days"] == [1, 2, 3, 4, 5]
    assert plan["enabled"] is True
    assert coordinator.departure_previous is None
    assert coordinator.departure_restore_at is None
    assert entity.extra_state_attributes is None


@pytest.mark.asyncio
async def test_automatic_restore_retries_a_refused_write(
    soon_button, scheduled_restores, monkeypatch
) -> None:
    """A car that refuses the write is retried instead of dropping the plan."""
    from datetime import datetime

    from custom_components.chery_europe import departure as departure_module
    from custom_components.chery_europe.exceptions import CheryEuropeException

    entity, coordinator = soon_button
    _freeze(
        monkeypatch,
        now=datetime(2026, 11, 25, 6, 0),
        utcnow=datetime(2026, 11, 25, 5, 0),
    )
    await entity.async_press()
    coordinator.api.send_travel_appointment = AsyncMock(
        side_effect=CheryEuropeException("the car is asleep")
    )

    await scheduled_restores[0][1](None)

    assert scheduled_restores[-1][0] == departure_module.RESTORE_RETRY_MINUTES * 60
    assert coordinator.departure_previous is not None


@pytest.mark.asyncio
async def test_the_restore_gives_up_after_the_last_attempt(
    soon_button, scheduled_restores, monkeypatch
) -> None:
    """The retries stop, the deadline is dropped and the failure is only logged."""
    from datetime import datetime

    from custom_components.chery_europe import departure as departure_module
    from custom_components.chery_europe.exceptions import CheryEuropeException

    entity, coordinator = soon_button
    _freeze(
        monkeypatch,
        now=datetime(2026, 11, 25, 6, 0),
        utcnow=datetime(2026, 11, 25, 5, 0),
    )
    await entity.async_press()
    coordinator.api.send_travel_appointment = AsyncMock(
        side_effect=CheryEuropeException("the car is asleep")
    )

    for _ in range(departure_module.RESTORE_MAX_ATTEMPTS):
        await scheduled_restores[-1][1](None)

    assert len(scheduled_restores) == departure_module.RESTORE_MAX_ATTEMPTS
    assert coordinator.departure_restore_at is None


@pytest.mark.asyncio
async def test_a_failed_press_leaves_nothing_behind(soon_button, scheduled_restores, monkeypatch) -> None:
    """When the car rejects the shift the timer and the snapshot are dropped."""
    from datetime import datetime

    from custom_components.chery_europe.exceptions import CheryEuropeCommandError

    entity, coordinator = soon_button
    _freeze(
        monkeypatch,
        now=datetime(2026, 11, 25, 6, 0),
        utcnow=datetime(2026, 11, 25, 5, 0),
    )
    coordinator.api.send_travel_appointment = AsyncMock(
        return_value={"ok": False, "message": "denied"}
    )

    with pytest.raises(CheryEuropeCommandError):
        await entity.async_press()

    assert coordinator.departure_previous is None
    assert coordinator.departure_restore_at is None
    assert scheduled_restores[0][2].called is True


@pytest.mark.asyncio
async def test_restore_resumes_after_a_restart(scheduled_restores, monkeypatch) -> None:
    """A deadline saved in the state attributes is turned back into a timer."""
    from datetime import datetime

    from custom_components.chery_europe import button as button_module

    coordinator = _coordinator([_departure_plan("07:30")], draft="06:15", armed=True)
    saved = {
        "travel_time": "07:30",
        "days": [1, 2, 3, 4, 5],
        "enabled": True,
    }
    _freeze(
        monkeypatch,
        now=datetime(2026, 11, 25, 6, 10),
        utcnow=datetime(2026, 11, 25, 5, 10),
    )
    entity = button_module.CheryEuropeDepartureSoonButton(coordinator, _entry())

    async def _last_state():
        return SimpleNamespace(
            attributes={
                "departure_previous": saved,
                "departure_restore_at": "2026-11-25T05:15:00",
            }
        )

    entity.async_get_last_state = _last_state
    await entity.async_added_to_hass()

    assert coordinator.departure_previous == saved
    assert scheduled_restores[0][0] == 5 * 60


@pytest.mark.asyncio
async def test_restore_after_a_restart_runs_at_once_when_overdue(
    scheduled_restores, monkeypatch
) -> None:
    """A deadline that passed while Home Assistant was down restores immediately."""
    from datetime import datetime

    from custom_components.chery_europe import button as button_module

    coordinator = _coordinator([_departure_plan("07:30")], draft="06:15", armed=True)
    _freeze(
        monkeypatch,
        now=datetime(2026, 11, 25, 6, 40),
        utcnow=datetime(2026, 11, 25, 5, 40),
    )
    entity = button_module.CheryEuropeDepartureSoonButton(coordinator, _entry())

    async def _last_state():
        return SimpleNamespace(
            attributes={
                "departure_previous": {
                    "travel_time": "07:30",
                    "days": [1],
                    "enabled": True,
                },
                "departure_restore_at": "2026-11-25T05:15:00",
            }
        )

    entity.async_get_last_state = _last_state
    await entity.async_added_to_hass()

    assert scheduled_restores[0][0] == 0
