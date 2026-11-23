"""Tests for the active-alert aggregation."""

from custom_components.chery_europe.alerts import (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    alerts_content,
    collect_alerts,
)
from custom_components.chery_europe.data import CheryData


def test_collect_alerts_returns_empty_for_clean_car():
    """A car without flags, open doors or warnings has no alerts."""
    assert collect_alerts(None) == []
    assert collect_alerts(CheryData(vin="VIN")) == []


def test_collect_alerts_reports_open_door_and_window():
    """Opening states become info alerts with readable texts."""
    data = CheryData(
        vin="VIN",
        door_front_left_open=True,
        window_rear_right_open=True,
        trunk_open=False,
    )

    alerts = collect_alerts(data, "en")

    assert [alert.key for alert in alerts] == ["door_front_left", "window_rear_right"]
    assert all(alert.severity == SEVERITY_INFO for alert in alerts)
    assert alerts[0].text == "Front left door is open"
    assert alerts[0].category == "door"


def test_collect_alerts_reports_car_warning_flags_first():
    """The car's own warning flags outrank opening states and use the UI language."""
    data = CheryData(
        vin="VIN",
        alert_tire_front_left=True,
        alert_soc_low=True,
        trunk_open=True,
    )

    alerts = collect_alerts(data, "pl")

    assert [alert.key for alert in alerts] == ["soc_low", "tire_front_left", "trunk"]
    assert alerts[0].severity == SEVERITY_WARNING
    assert alerts[0].text == "Niski poziom naładowania baterii trakcyjnej"
    assert alerts[2].text == "Otwarta klapa bagażnika"


def test_collect_alerts_falls_back_to_english():
    """An unknown UI language falls back to the English message table."""
    data = CheryData(vin="VIN", alert_oil_service=True)

    assert collect_alerts(data, "de")[0].text == "Oil service reminder"
    assert collect_alerts(data, None)[0].text == "Oil service reminder"


def test_collect_alerts_ignores_inactive_flags():
    """A cleared (0) warning flag produces no alert."""
    data = CheryData(
        vin="VIN",
        alert_tire_rear_left=False,
        alert_electricity=False,
        door_rear_right_open=False,
    )

    assert collect_alerts(data, "pl") == []


def test_alerts_content_joins_texts():
    """The content sensor shows one alert per line and stays empty when clean."""
    data = CheryData(vin="VIN", door_front_left_open=True, alert_soc_low=True)

    alerts = collect_alerts(data, "pl")

    assert alerts_content(alerts) == (
        "Niski poziom naładowania baterii trakcyjnej\nOtwarte drzwi przednie lewe"
    )
    assert alerts_content([], empty="Brak") == "Brak"
