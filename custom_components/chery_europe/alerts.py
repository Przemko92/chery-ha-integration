"""Active vehicle alerts built from the telemetry we already poll.

The Chery app shows two kinds of "alerts":

* the car's own warning flags (``*Call`` fields in the status payload, e.g.
  ``lFrontTyreCall``, ``socLowCall``, ``oilCall``) and
* the opening states of doors, windows, the trunk and the sunroof.

Both are already part of the status document the coordinator polls, so this
module is stateless and needs no extra API request.  Cloud messages from the
message centre (``msgCenter``) are pushed over MQTT only; their envelope has
not been observed yet, so they are not part of this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from .data import CheryData

SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

CATEGORY_TYRE = "tyre"
CATEGORY_BATTERY = "battery"
CATEGORY_SERVICE = "service"
CATEGORY_ELECTRICAL = "electrical"
CATEGORY_DOOR = "door"
CATEGORY_WINDOW = "window"
CATEGORY_BODY = "body"

#: Alert texts per language.  The first language is the fallback.
MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "tire_front_left": "Low tyre pressure: front left",
        "tire_front_right": "Low tyre pressure: front right",
        "tire_rear_left": "Low tyre pressure: rear left",
        "tire_rear_right": "Low tyre pressure: rear right",
        "soc_low": "Traction battery charge is low",
        "oil_service": "Oil service reminder",
        "electricity": "Vehicle electrical system warning",
        "door_front_left": "Front left door is open",
        "door_front_right": "Front right door is open",
        "door_rear_left": "Rear left door is open",
        "door_rear_right": "Rear right door is open",
        "trunk": "Trunk is open",
        "window_front_left": "Front left window is open",
        "window_front_right": "Front right window is open",
        "window_rear_left": "Rear left window is open",
        "window_rear_right": "Rear right window is open",
        "sunroof": "Sunroof is open",
    },
    "pl": {
        "tire_front_left": "Niskie ciśnienie w oponie: przednia lewa",
        "tire_front_right": "Niskie ciśnienie w oponie: przednia prawa",
        "tire_rear_left": "Niskie ciśnienie w oponie: tylna lewa",
        "tire_rear_right": "Niskie ciśnienie w oponie: tylna prawa",
        "soc_low": "Niski poziom naładowania baterii trakcyjnej",
        "oil_service": "Przypomnienie o serwisie oleju",
        "electricity": "Ostrzeżenie układu elektrycznego pojazdu",
        "door_front_left": "Otwarte drzwi przednie lewe",
        "door_front_right": "Otwarte drzwi przednie prawe",
        "door_rear_left": "Otwarte drzwi tylne lewe",
        "door_rear_right": "Otwarte drzwi tylne prawe",
        "trunk": "Otwarta klapa bagażnika",
        "window_front_left": "Otwarte okno przednie lewe",
        "window_front_right": "Otwarte okno przednie prawe",
        "window_rear_left": "Otwarte okno tylne lewe",
        "window_rear_right": "Otwarte okno tylne prawe",
        "sunroof": "Otwarty szyberdach",
    },
}

#: ``(key, category, severity, data field)`` for the state-derived alerts.
STATE_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("tire_front_left", CATEGORY_TYRE, SEVERITY_WARNING, "alert_tire_front_left"),
    ("tire_front_right", CATEGORY_TYRE, SEVERITY_WARNING, "alert_tire_front_right"),
    ("tire_rear_left", CATEGORY_TYRE, SEVERITY_WARNING, "alert_tire_rear_left"),
    ("tire_rear_right", CATEGORY_TYRE, SEVERITY_WARNING, "alert_tire_rear_right"),
    ("soc_low", CATEGORY_BATTERY, SEVERITY_WARNING, "alert_soc_low"),
    ("oil_service", CATEGORY_SERVICE, SEVERITY_WARNING, "alert_oil_service"),
    ("electricity", CATEGORY_ELECTRICAL, SEVERITY_WARNING, "alert_electricity"),
    ("door_front_left", CATEGORY_DOOR, SEVERITY_INFO, "door_front_left_open"),
    ("door_front_right", CATEGORY_DOOR, SEVERITY_INFO, "door_front_right_open"),
    ("door_rear_left", CATEGORY_DOOR, SEVERITY_INFO, "door_rear_left_open"),
    ("door_rear_right", CATEGORY_DOOR, SEVERITY_INFO, "door_rear_right_open"),
    ("trunk", CATEGORY_BODY, SEVERITY_INFO, "trunk_open"),
    ("window_front_left", CATEGORY_WINDOW, SEVERITY_INFO, "window_front_left_open"),
    ("window_front_right", CATEGORY_WINDOW, SEVERITY_INFO, "window_front_right_open"),
    ("window_rear_left", CATEGORY_WINDOW, SEVERITY_INFO, "window_rear_left_open"),
    ("window_rear_right", CATEGORY_WINDOW, SEVERITY_INFO, "window_rear_right_open"),
    ("sunroof", CATEGORY_BODY, SEVERITY_INFO, "sunroof_open"),
)

_SEVERITY_ORDER = {SEVERITY_WARNING: 0, SEVERITY_INFO: 1}


@dataclass(frozen=True, slots=True)
class CheryAlert:
    """One active alert with the text the app would show."""

    key: str
    category: str
    severity: str
    text: str

    def as_dict(self) -> dict[str, str]:
        """Return the alert as a plain dict for entity attributes."""
        return {
            "key": self.key,
            "category": self.category,
            "severity": self.severity,
            "text": self.text,
        }


def _messages(language: str | None) -> dict[str, str]:
    """Return the message table for a language, falling back to English."""
    code = (language or "en").split("-")[0].lower()
    return MESSAGES.get(code, MESSAGES["en"])


def collect_alerts(data: CheryData | None, language: str | None = None) -> list[CheryAlert]:
    """Return the active alerts sorted by severity, then by key."""
    if data is None:
        return []
    messages = _messages(language)
    alerts: list[CheryAlert] = []
    for key, category, severity, field in STATE_RULES:
        if getattr(data, field, None) is True:
            alerts.append(
                CheryAlert(key=key, category=category, severity=severity, text=messages[key])
            )
    alerts.sort(key=lambda alert: (_SEVERITY_ORDER.get(alert.severity, 9), alert.key))
    return alerts


def collect_warnings(data: CheryData | None, language: str | None = None) -> list[CheryAlert]:
    """Return only the car's own warning flags (tyres, battery, service, electrical)."""
    return [
        alert
        for alert in collect_alerts(data, language)
        if alert.severity == SEVERITY_WARNING
    ]


def alerts_content(alerts: list[CheryAlert], *, empty: str = "") -> str:
    """Return the alert texts joined for display (``empty`` when none)."""
    if not alerts:
        return empty
    return "\n".join(alert.text for alert in alerts)
