from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.const import CONF_PIN
from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.select import VENT_SELECT_DESCRIPTIONS, CheryEuropeVentSelect


def _make_select(key: str, data: CheryData):
    coordinator = SimpleNamespace(
        data=data,
        last_update_success=True,
        api=SimpleNamespace(send_command=AsyncMock(return_value={"ok": True})),
        async_set_updated_data=Mock(),
        schedule_refresh_after_command=Mock(),
    )
    entry = SimpleNamespace(entry_id="entry-1", options={CONF_PIN: "1234"})
    description = next(item for item in VENT_SELECT_DESCRIPTIONS if item.key == key)
    select = CheryEuropeVentSelect(coordinator, description, entry)
    return select, coordinator


def test_sunroof_select_reports_tilt_option():
    select, _ = _make_select("sunroof", CheryData(vin="VIN1", sunroof_position=50))
    assert select.current_option == "tilt"


def test_sunroof_select_reports_closed_option():
    select, _ = _make_select("sunroof", CheryData(vin="VIN1", sunroof_position=0))
    assert select.current_option == "closed"


def test_sunroof_select_hides_tilt_option_when_open():
    select, _ = _make_select("sunroof", CheryData(vin="VIN1", sunroof_position=100))
    assert select.options == ["closed", "open"]


def test_sunroof_select_shows_tilt_option_when_not_open():
    select, _ = _make_select("sunroof", CheryData(vin="VIN1", sunroof_position=0))
    assert select.options == ["closed", "tilt", "open"]


@pytest.mark.asyncio
async def test_sunroof_select_tilt_option_sends_tilt_action():
    select, coordinator = _make_select("sunroof", CheryData(vin="VIN1", sunroof_position=0))

    await select.async_select_option("tilt")

    coordinator.api.send_command.assert_awaited_once()
    call = coordinator.api.send_command.await_args
    assert call.args == ("VIN1", "ve_1207", "1234")
    assert call.kwargs["action"] == "tilt"


def test_windows_select_reports_most_open_window():
    select, _ = _make_select(
        "windows",
        CheryData(
            vin="VIN1",
            window_front_left_position=0,
            window_front_right_position=50,
            window_rear_left_position=0,
            window_rear_right_position=0,
        ),
    )
    assert select.current_option == "vent"


def test_windows_select_always_shows_vent_option():
    select, _ = _make_select(
        "windows",
        CheryData(
            vin="VIN1",
            window_front_left_position=100,
            window_front_right_position=100,
            window_rear_left_position=100,
            window_rear_right_position=100,
        ),
    )
    assert select.options == ["closed", "vent", "open"]


@pytest.mark.asyncio
async def test_windows_select_vent_option_sends_vent_action():
    select, coordinator = _make_select(
        "windows",
        CheryData(
            vin="VIN1",
            window_front_left_position=0,
            window_front_right_position=0,
            window_rear_left_position=0,
            window_rear_right_position=0,
        ),
    )

    await select.async_select_option("vent")

    coordinator.api.send_command.assert_awaited_once()
    call = coordinator.api.send_command.await_args
    assert call.args == ("VIN1", "ve_1206", "1234")
    assert call.kwargs["action"] == "vent"
