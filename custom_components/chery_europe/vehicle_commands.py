"""Build tspconsole vehicle-control requests for Chery Europe."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

DEFAULT_AIR_DURATION = "15"
DEFAULT_AIR_TEMPERATURE = "22.0"
DEFAULT_CHARGE_START_MINUTES = 480
DEFAULT_CHARGE_DURATION_HOURS = 6
DEFAULT_CHARGE_CYCLE_DAYS = [1, 2, 3, 4, 5, 6, 7]

TSP_COMMAND_SUCCESS = frozenset({"000000", "A00079", 0})


@dataclass(frozen=True)
class VehicleCommandSpec:
    """Describe how to map a legacy command id to a tspconsole endpoint."""

    endpoint: str
    build_body: Callable[[dict[str, Any]], dict[str, str]]


def build_air_control_body(values: dict[str, Any]) -> dict[str, str]:
    enabled = values.get("enabled", True)
    temperature = values.get("temperature", DEFAULT_AIR_TEMPERATURE)
    if isinstance(temperature, (int, float)):
        temperature = f"{float(temperature):.1f}"
    duration = str(values.get("duration", DEFAULT_AIR_DURATION))
    body = {
        "airControlType": "1" if enabled else "0",
        "airType": "1",
        "temperature": str(temperature),
        "times": duration,
    }
    return body


def build_lock_control_body(values: dict[str, Any]) -> dict[str, str]:
    action = str(values.get("action", "lock")).lower()
    return {"lockType": "1" if action == "unlock" else "0"}


def build_front_windshield_body(values: dict[str, Any]) -> dict[str, str]:
    enabled = values.get("enabled", True)
    body = {"frontWindshieldHeat": "1" if enabled else "0"}
    if enabled:
        body["times"] = str(values.get("duration", DEFAULT_AIR_DURATION))
    return body


def build_rear_defrost_body(values: dict[str, Any]) -> dict[str, str]:
    enabled = values.get("enabled", True)
    body = {"backDefrosting": "1" if enabled else "0"}
    if enabled:
        body["times"] = str(values.get("duration", DEFAULT_AIR_DURATION))
    return body


def build_charge_plan(
    *,
    switch_status: int,
    start_minutes: int = DEFAULT_CHARGE_START_MINUTES,
    duration_hours: int = DEFAULT_CHARGE_DURATION_HOURS,
) -> dict[str, Any]:
    """Build one chargeAppointPlans entry for chargeAppointControl."""
    return {
        "cycleData": list(DEFAULT_CHARGE_CYCLE_DAYS),
        "startTime": int(start_minutes),
        "switchStatus": int(switch_status),
        "timeConsuming": int(duration_hours) * 60,
    }


def build_charge_appoint_body(values: dict[str, Any]) -> dict[str, Any]:
    """Build the nested body for scheduled charging."""
    enabled = values.get("enabled", True)
    start_minutes = int(values.get("start_minutes", DEFAULT_CHARGE_START_MINUTES))
    duration_hours = int(values.get("duration_hours", DEFAULT_CHARGE_DURATION_HOURS))
    switch_status = 1 if enabled else 0
    return {
        "mainSwitch": 1 if enabled else 0,
        "chargeAppointPlans": [
            build_charge_plan(
                switch_status=switch_status,
                start_minutes=start_minutes,
                duration_hours=duration_hours,
            )
        ],
    }


def build_charge_start_stop_body(values: dict[str, Any]) -> dict[str, str]:
    enabled = values.get("enabled", True)
    return {"controlType": "1" if enabled else "0"}


COMMAND_SPECS: dict[str, VehicleCommandSpec] = {
    "ve_1104": VehicleCommandSpec("airControl", build_air_control_body),
    "ve_1105": VehicleCommandSpec("lockControl", build_lock_control_body),
    "ve_1103": VehicleCommandSpec("frontWindshieldControl", build_front_windshield_body),
    "ve_1135": VehicleCommandSpec("backDefrostingControl", build_rear_defrost_body),
    "ve_1201": VehicleCommandSpec("chargeStartStopControl", build_charge_start_stop_body),
    "ve_1202": VehicleCommandSpec("chargeAppointControl", build_charge_appoint_body),
}


def command_result(response: Any) -> dict[str, Any]:
    """Normalize a tspconsole command response for Home Assistant services."""
    if not isinstance(response, dict):
        return {"ok": False, "message": "Invalid command response"}

    code = response.get("code")
    message = response.get("msg") or response.get("message") or response.get("key")
    ok = code in TSP_COMMAND_SUCCESS or response.get("ok") is True
    return {
        "ok": ok,
        "code": code,
        "message": message,
        "response": response,
    }
