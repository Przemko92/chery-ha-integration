"""Departure appointment: ``travelQuery`` read against ``appointmentTravel`` write."""

import datetime
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.data import (
    CheryData,
    apply_travel_appointment,
    parse_appointment_plans,
    parse_travel_appointment,
)
from custom_components.chery_europe.vehicle_commands import build_travel_appoint_body

# Verbatim answer of POST /asd/travelManage/travelQuery on 2026-11-24 (CET), the
# plan the app displays as 08:55 every day.
TRAVEL_QUERY = {
    "code": "000000",
    "body": {
        "appointmentTravelSetVOS": [
            {
                "travelTime": 475,
                "travelDate": [1, 2, 3, 4, 5, 6, 7],
                "travelAppointMainId": 49957,
                "switcher": 1,
                "id": 452903971,
            }
        ],
        "mainSwitcher": 1,
        "vin": "VIN123",
        "id": 49957,
    },
}


@pytest.fixture
def warsaw():
    """Run the test in the user's zone, which is what the app shows."""
    from homeassistant.util import dt as dt_util

    zone = ZoneInfo("Europe/Warsaw")
    dt_util.set_default_time_zone(zone)
    try:
        yield zone
    finally:
        dt_util.set_default_time_zone(datetime.UTC)


def _offset(zone: ZoneInfo) -> int:
    offset = datetime.datetime.now(zone).utcoffset()
    assert offset is not None
    return int(offset.total_seconds() // 60)


def test_travel_query_minutes_are_utc_and_read_back_as_local(warsaw):
    plans = parse_appointment_plans(TRAVEL_QUERY)

    assert plans is not None and len(plans) == 1
    plan = plans[0]
    local = (475 + _offset(warsaw)) % 1440
    assert plan["travel_time"] == f"{local // 60:02d}:{local % 60:02d}"
    assert plan["days"] == [1, 2, 3, 4, 5, 6, 7]
    assert plan["enabled"] is True
    assert plan["plan_id"] == "452903971"
    assert plan["name"] == "Wyjazd"


def test_the_time_entity_and_the_write_agree(warsaw):
    """What the read shows must be what the write stores, and vice versa."""
    plans = parse_appointment_plans(TRAVEL_QUERY)
    assert plans is not None
    local_time = plans[0]["travel_time"]

    body = build_travel_appoint_body({"vin": "VIN123", "plans": plans})
    wire = body["appointmentTravelAOS"][0]["travelTime"]

    assert wire == str(475)
    assert body["mainSwitcher"] == "1"
    weekdays = body["appointmentTravelAOS"][0]["travelWeekday"]
    assert weekdays == ["1", "2", "3", "4", "5", "6", "7"]
    shown = (475 + _offset(warsaw)) % 1440
    assert local_time == f"{shown // 60:02d}:{shown % 60:02d}"


def test_an_evening_departure_does_not_wrap_the_wrong_way(warsaw):
    """23:30 local in CET is 22:30 UTC, not 00:30 the next day."""
    body = build_travel_appoint_body(
        {
            "vin": "V",
            "plans": [
                {
                    "name": "Wyjazd",
                    "travel_time": "23:30",
                    "days": [1],
                    "enabled": True,
                }
            ],
        }
    )
    wire = int(body["appointmentTravelAOS"][0]["travelTime"])
    assert wire == (1410 - _offset(warsaw)) % 1440

    read = parse_appointment_plans(
        {"body": {"appointmentTravelSetVOS": [{"travelTime": wire, "travelDate": [1]}]}}
    )
    assert read is not None and read[0]["travel_time"] == "23:30"


def test_main_switcher_off_reports_the_plan_as_disarmed():
    payload = {
        "body": {
            "mainSwitcher": "0",
            "appointmentTravelSetVOS": [{"travelTime": 475, "switcher": "1"}],
        }
    }
    plans = parse_appointment_plans(payload)
    assert plans is not None and plans[0]["enabled"] is False


def test_prepare_plans_still_parse_for_cars_that_answer_them():
    payload = {
        "body": {
            "preparePlans": [
                {"planName": "Work", "travelTime": "06:30", "cycleData": [1, 2]}
            ]
        }
    }
    plans = parse_travel_appointment(payload)
    assert plans is not None and plans[0]["travel_time"] == "06:30"


def test_travel_query_wins_over_an_empty_prepare_list():
    payload = {
        "body": {
            "preparePlans": [],
            "appointmentTravelSetVOS": [{"travelTime": 475, "travelDate": [1]}],
        }
    }
    plans = parse_travel_appointment(payload)
    assert plans is not None and len(plans) == 1


def test_an_answer_without_plans_keeps_the_last_known_state():
    assert parse_appointment_plans({"code": "000000"}) is None
    assert parse_appointment_plans({"body": {"vin": "V"}}) is None
    assert parse_appointment_plans("nope") is None


def test_next_departure_is_computed_on_the_local_clock(warsaw):
    """The plan time is local, so the next run must not be built from UTC now.

    Building it from ``datetime.now(timezone.utc)`` shifted the sensor by the
    current UTC offset (09:55 instead of 08:55 in CET).
    """
    plans = parse_travel_appointment(TRAVEL_QUERY)
    assert plans is not None

    data = apply_travel_appointment(CheryData(vin="V"), plans)

    assert data.prepare_next_departure is not None
    upcoming = datetime.datetime.fromisoformat(data.prepare_next_departure)
    assert upcoming.tzinfo is not None
    local = upcoming.astimezone(warsaw)
    hour, minute = (int(part) for part in plans[0]["travel_time"].split(":"))
    assert (local.hour, local.minute) == (hour, minute)
