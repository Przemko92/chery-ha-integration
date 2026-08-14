"""Adapt vehicle-control commands to what this vehicle is allowed to send.

The backend validates each command body against ``queryVehicleAuthority``.
Unknown or unread permissions are treated as allowed (fail open), matching
the official app and the Omoda integration.
"""

from __future__ import annotations

from typing import Any

from .exceptions import CheryEuropePermissionError

UNKNOWN: dict[int, int] = {}

ENDPOINT_CATEGORY = {
    "airControl": 204,
    "heatingControl": 209,
    "coolingControl": 210,
    "seatControl": 214,
    "frontWindshieldControl": 215,
    "backDefrostingControl": 232,
    "steeringWheelControl": 208,
    "lockControl": 203,
    "powerLiftgateControl": 205,
    "windowControl": 206,
    "skylightControl": 207,
    "chargeStartStopControl": 220,
    "chargeAppointControl": 213,
    "findCar": 202,
    "vehicleLocation": 211,
}

PRUNABLE_FIELDS = {
    "airControl": {
        "frontDefrosting": 2045,
        "airPurControlType": 2046,
        "mSeatHeating": 2047,
        "pSeatHeating": 2048,
        "mSeatAiry": 2049,
        "pSeatAiry": 20410,
        "backDefrosting": 20411,
        "blSeatHeating": 20412,
        "brSeatHeating": 20413,
        "blSeatAiry": 20414,
        "brSeatAiry": 20415,
        "frontWindshieldHeat": 20416,
    },
}

BASE_VOICE = {"airControl": 2041}

FALLBACK = {
    ("backDefrostingControl", "backDefrosting"): (2321, 20411),
    ("frontWindshieldControl", "frontWindshieldHeat"): (2151, 20416),
    ("seatControl", "mSeatHeating"): (2141, 2047),
    ("seatControl", "pSeatHeating"): (2142, 2048),
    ("seatControl", "mSeatAiry"): (2143, 2049),
    ("seatControl", "pSeatAiry"): (2144, 20410),
    ("seatControl", "blSeatHeating"): (2145, 20412),
    ("seatControl", "brSeatHeating"): (2146, 20413),
    ("seatControl", "blSeatAiry"): (2147, 20414),
    ("seatControl", "brSeatAiry"): (2148, 20415),
}

BASE_AIRCONTROL = {"airType": "1", "temperature": "21.0", "times": "15"}

CYCLE_RULES = {
    "chargeAppointControl": (2131, 2132, "cycleData"),
}


def normalize_permissions(payload: Any) -> dict[int, int]:
    """Convert a queryVehicleAuthority response to ``{id: state}``."""
    data = payload.get("data") if isinstance(payload, dict) else payload
    items = data.get("permissionList") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        return UNKNOWN
    out: dict[int, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        voice_id = _as_int(item.get("id"))
        state = _as_int(item.get("state"))
        if voice_id is not None and state is not None:
            out[voice_id] = state
    return out or UNKNOWN


def allowed(perms: dict[int, int], voice: int | None) -> bool:
    """Unknown voices are allowed so a missing list never hides a function."""
    if not perms or voice is None:
        return True
    return perms.get(voice, 1) != 0


def category_denied(endpoint: str, perms: dict[int, int]) -> bool:
    return not allowed(perms, ENDPOINT_CATEGORY.get(endpoint))


def adapt_command(
    endpoint: str,
    body: dict[str, Any],
    perms: dict[int, int],
) -> tuple[str, dict[str, Any]]:
    """Return the endpoint/body this vehicle is allowed to send."""
    if not perms:
        return endpoint, body

    cycle_error = _cycle_error(endpoint, body, perms)
    if cycle_error:
        raise CheryEuropePermissionError(cycle_error)

    endpoint, body = _reroute(endpoint, body, perms)
    if category_denied(endpoint, perms) or not allowed(perms, BASE_VOICE.get(endpoint)):
        raise CheryEuropePermissionError(
            f"This vehicle does not allow the {endpoint} command"
        )
    return endpoint, _prune(endpoint, body, perms)


def _reroute(
    endpoint: str,
    body: dict[str, Any],
    perms: dict[int, int],
) -> tuple[str, dict[str, Any]]:
    for field in list(body):
        rule = FALLBACK.get((endpoint, field))
        if not rule:
            continue
        dedicated, alternative = rule
        if allowed(perms, dedicated) and not category_denied(endpoint, perms):
            return endpoint, body
        if not allowed(perms, alternative) or category_denied("airControl", perms):
            return endpoint, body
        enabled = str(body.get(field, "0")).strip() not in {"0", "", "false", "False"}
        routed = dict(BASE_AIRCONTROL)
        routed["airControlType"] = "1" if enabled else "0"
        routed[field] = body[field]
        return "airControl", routed
    return endpoint, body


def _prune(
    endpoint: str,
    body: dict[str, Any],
    perms: dict[int, int],
) -> dict[str, Any]:
    table = PRUNABLE_FIELDS.get(endpoint)
    if not table:
        return body
    skipped = [field for field in body if field in table and not allowed(perms, table[field])]
    if not skipped:
        return body
    return {key: value for key, value in body.items() if key not in skipped}


def _cycle_error(endpoint: str, body: dict[str, Any], perms: dict[int, int]) -> str | None:
    rule = CYCLE_RULES.get(endpoint)
    if not rule:
        return None
    custom_voice, week_voice, field = rule
    days = _days(body, field)
    if not days:
        return None
    weekly = len(days) == 7
    if allowed(perms, week_voice if weekly else custom_voice):
        return None
    kind = "every day of the week" if weekly else "selected days"
    return f"This vehicle does not allow scheduled charging for {kind}"


def _days(body: dict[str, Any], field: str) -> list[Any] | None:
    value = body.get(field)
    if isinstance(value, list):
        return value
    for item in body.values():
        if isinstance(item, list):
            for entry in item:
                if isinstance(entry, dict) and isinstance(entry.get(field), list):
                    return entry[field]
    return None


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
