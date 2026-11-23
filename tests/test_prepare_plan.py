"""Tests for the scheduled cabin/battery preparation plan helpers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from custom_components.chery_europe.prepare_plan import (
    MAX_PLANS,
    build_plan,
    disable_plan,
    merge_plan,
    next_departure,
    next_run,
    normalize_days,
    normalize_temperature,
    normalize_travel_time,
    parse_plans,
    travel_minutes,
    validate_plans,
)


def _plan(name: str = "Work", travel_time: str = "07:30", **kwargs) -> dict:
    return build_plan(name=name, travel_time=travel_time, **kwargs)


def test_travel_time_accepts_hhmm_and_clock_formats() -> None:
    assert normalize_travel_time("0730") == "07:30"
    assert normalize_travel_time("7:30") == "07:30"
    assert normalize_travel_time("23:59") == "23:59"
    with pytest.raises(ValueError):
        normalize_travel_time("noon")


def test_travel_minutes_is_not_hh_mm_times_hundred() -> None:
    # Regression: "0730" used to be read as 730 minutes.
    assert travel_minutes("0730") == 450
    assert travel_minutes("07:30") == 450


def test_temperature_is_normalised_to_one_decimal() -> None:
    assert normalize_temperature(22) == "22.0"
    assert normalize_temperature("21.5") == "21.5"
    assert normalize_temperature(None) is None
    with pytest.raises(ValueError):
        normalize_temperature(40)


def test_normalize_days_modes() -> None:
    assert normalize_days("daily") == [1, 2, 3, 4, 5, 6, 7]
    assert normalize_days("workdays") == [1, 2, 3, 4, 5]
    assert normalize_days("weekend") == [6, 7]
    assert normalize_days("custom", [3, 1, 3]) == [1, 3]
    with pytest.raises(ValueError):
        normalize_days("custom", [])
    with pytest.raises(ValueError):
        normalize_days("custom", [0])
    with pytest.raises(ValueError):
        normalize_days("sometimes")


def test_build_plan_defaults() -> None:
    plan = _plan()
    assert plan["days"] == [1, 2, 3, 4, 5, 6, 7]
    assert plan["enabled"] is True
    assert plan["temperature"] is None
    assert plan["plan_id"] is None
    assert set(plan["features"]) >= {"battery_heat", "steering_wheel_heat"}


def test_plan_name_is_limited_to_ten_characters() -> None:
    with pytest.raises(ValueError):
        _plan(name="Bardzo dluga nazwa")
    with pytest.raises(ValueError):
        _plan(name="   ")


def test_validate_rejects_duplicate_name_and_close_departures() -> None:
    plans = [_plan("Work", "07:30")]
    with pytest.raises(ValueError, match="already exists"):
        validate_plans(plans, _plan("Work", "12:00"))
    with pytest.raises(ValueError, match="at least 20 minutes"):
        validate_plans(plans, _plan("Gym", "07:45"))
    validate_plans(plans, _plan("Gym", "07:50"))


def test_validate_rejects_sixth_active_plan() -> None:
    plans = [
        _plan(f"P{index}", f"{6 + index:02d}:00") for index in range(MAX_PLANS)
    ]
    with pytest.raises(ValueError, match="at most"):
        validate_plans(plans, _plan("Extra", "20:00"))


def test_validate_allows_replacing_a_disabled_plan() -> None:
    plans = [
        _plan(f"P{index}", f"{6 + index:02d}:00", plan_id=str(index))
        for index in range(MAX_PLANS)
    ]
    disabled = disable_plan(plans, "0")
    replacement = build_plan(
        name="P0", travel_time="06:00", plan_id="0"
    )
    validate_plans(disabled, replacement)


def test_merge_plan_replaces_by_id_and_appends_new() -> None:
    plans = [_plan("Work", "07:30", plan_id="11")]
    updated = merge_plan(plans, _plan("Work2", "08:30", plan_id="11"))
    assert len(updated) == 1
    assert updated[0]["name"] == "Work2"
    added = merge_plan(plans, _plan("Gym", "18:00"))
    assert len(added) == 2


def test_disable_plan_turns_everything_off() -> None:
    plans = [_plan("Work", "07:30", plan_id="11", battery_heat=True)]
    result = disable_plan(plans, "11")
    assert result[0]["enabled"] is False
    assert all(value is False for value in result[0]["features"].values())
    with pytest.raises(ValueError, match="Unknown plan_id"):
        disable_plan(plans, "99")
    with pytest.raises(ValueError):
        disable_plan(plans, None)


def test_next_run_respects_weekdays_and_time_of_day() -> None:
    monday_morning = datetime(2026, 11, 23, 6, 0, tzinfo=timezone.utc)
    workdays = _plan("Work", "07:30", repeat="workdays")
    assert next_run(workdays, monday_morning) == datetime(
        2026, 11, 23, 7, 30, tzinfo=timezone.utc
    )
    # Monday 08:00 is past today's departure, so the next one is Tuesday.
    assert next_run(workdays, datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc)) == (
        datetime(2026, 11, 24, 7, 30, tzinfo=timezone.utc)
    )
    weekend = _plan("Trip", "09:00", repeat="weekend")
    assert next_run(weekend, monday_morning) == datetime(
        2026, 11, 28, 9, 0, tzinfo=timezone.utc
    )


def test_next_departure_picks_the_earliest_enabled_plan() -> None:
    now = datetime(2026, 11, 23, 6, 0, tzinfo=timezone.utc)
    plans = [
        _plan("Late", "09:00", plan_id="1"),
        _plan("Early", "06:45", plan_id="2"),
        build_plan(name="Off", travel_time="06:30", plan_id="3", enabled=False),
    ]
    assert next_departure(plans, now) == datetime(
        2026, 11, 23, 6, 45, tzinfo=timezone.utc
    )
    assert next_departure([], now) is None


def test_parse_plans_reads_the_wire_shape() -> None:
    payload = {
        "code": "000000",
        "data": {
            "preparePlans": [
                {
                    "planId": "abc",
                    "planName": "Work",
                    "travelTime": "07:30",
                    "cycleData": [1, 2, 3, 4, 5],
                    "switchStatus": 1,
                    "temperature": "22.0",
                    "batteryPackHeat": "1",
                    "steerWheelHeatSwitch": "0",
                    "pSeatHeating": "3",
                    "frontDefrosting": "1",
                }
            ]
        },
    }
    plans = parse_plans(payload)
    assert plans is not None and len(plans) == 1
    plan = plans[0]
    assert plan["plan_id"] == "abc"
    assert plan["travel_time"] == "07:30"
    assert plan["days"] == [1, 2, 3, 4, 5]
    assert plan["enabled"] is True
    assert plan["features"]["battery_heat"] is True
    assert plan["features"]["steering_wheel_heat"] is False
    assert plan["features"]["driver_seat_heat"] is True
    assert plan["features"]["front_defrost"] is True
    assert plan["features"]["rear_defrost"] is False


def test_parse_plans_returns_none_when_the_payload_is_empty() -> None:
    # None (not []) so the coordinator keeps the last known plans.
    assert parse_plans({"code": "000000", "data": {}}) is None
    assert parse_plans(None) is None
    assert parse_plans({"data": {"preparePlans": []}}) == []


def test_parse_plans_unwraps_the_tspconsole_body_envelope() -> None:
    """prepareQuery answers {"code","sign","body":{...}} - see live probe."""
    payload = {
        "code": "000000",
        "sign": "T70OYDCEF8GGFGQ1P/B0YDX9LSMSKNVWJ29IXSVCW7U=",
        "body": {
            "preparePlans": [
                {"planName": "Work", "travelTime": "07:30", "switchStatus": "1"}
            ],
            "vin": "LNNBBDEE1SD407504",
        },
    }
    plans = parse_plans(payload)
    assert plans is not None and [plan["name"] for plan in plans] == ["Work"]
    # An empty list is a real answer (no plans stored in the car), not a failure.
    assert parse_plans({"code": "000000", "body": {"preparePlans": []}}) == []


def test_parse_plans_accepts_a_bare_list_and_a_single_plan() -> None:
    single = {"planName": "Work", "travelTime": "07:30", "switchStatus": "1"}
    wrapped = parse_plans({"data": single})
    assert wrapped is not None and [plan["name"] for plan in wrapped] == ["Work"]
    listed = parse_plans({"data": [single, {"nope": 1}]})
    assert listed is not None and len(listed) == 1
