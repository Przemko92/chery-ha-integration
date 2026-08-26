import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.vehicle_commands import (
    build_air_control_body,
    build_charge_appoint_body,
    build_charge_plan,
    build_charge_start_stop_body,
    build_control_type_body,
    build_lock_control_body,
    build_seat_control_body,
    build_skylight_body,
    command_result,
)


def test_build_air_control_body_on():
    body = build_air_control_body({"enabled": True, "temperature": 22})
    assert body == {
        "airControlType": "1",
        "airType": "1",
        "temperature": "22.0",
        "times": "15",
    }


def test_build_air_control_body_off():
    body = build_air_control_body({"enabled": False, "temperature": 21.5})
    assert body["airControlType"] == "0"


def test_build_lock_control_body_unlock():
    body = build_lock_control_body({"action": "unlock"})
    assert body == {"lockType": "1"}


def test_build_charge_start_stop_body():
    assert build_charge_start_stop_body({"enabled": True}) == {"controlType": "1"}
    assert build_charge_start_stop_body({"enabled": False}) == {"controlType": "0"}


def test_build_charge_plan():
    plan = build_charge_plan(
        switch_status=1,
        start_minutes=465,
        duration_hours=6,
    )
    assert plan == {
        "cycleData": [1, 2, 3, 4, 5, 6, 7],
        "startTime": 465,
        "switchStatus": 1,
        "timeConsuming": 360,
    }


def test_build_charge_appoint_body_on():
    body = build_charge_appoint_body(
        {
            "enabled": True,
            "start_minutes": 480,
            "duration_hours": 8,
        }
    )
    assert body["mainSwitch"] == 1
    assert body["chargeAppointPlans"][0]["startTime"] == 480
    assert body["chargeAppointPlans"][0]["timeConsuming"] == 480


def test_build_charge_appoint_body_off():
    body = build_charge_appoint_body({"enabled": False})
    assert body["mainSwitch"] == 0
    assert body["chargeAppointPlans"][0]["switchStatus"] == 0


def test_command_result_success():
    assert command_result({"code": "A00079"})["ok"] is True


def test_command_result_failure():
    result = command_result({"code": 1, "msg": "try later", "key": "try.again.later"})
    assert result["ok"] is False
    assert result["message"] == "try later"


def test_build_seat_control_body():
    body = build_seat_control_body({"enabled": True, "seat_field": "pSeatHeating"})
    assert body["pSeatHeating"] == "3"
    assert body["times"] == "15"


def test_build_window_and_skylight_bodies():
    assert build_control_type_body({"action": "open"}) == {"controlType": "1"}
    assert build_control_type_body({"action": "close"}) == {"controlType": "0"}
    assert build_control_type_body({"action": "vent"}) == {"controlType": "2"}
    assert build_skylight_body({"action": "open"}) == {
        "controlType": "1",
        "skylightType": "1",
        "times": "1",
    }
    assert build_skylight_body({"action": "close"}) == {
        "controlType": "0",
        "skylightType": "1",
    }
    assert build_skylight_body({"action": "tilt"}) == {
        "controlType": "2",
        "skylightType": "1",
    }
