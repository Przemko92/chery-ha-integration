from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.const import CONF_PIN
from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.select import (
    SEAT_SELECT_DESCRIPTIONS,
    VENT_SELECT_DESCRIPTIONS,
    CheryEuropeSeatSelect,
    CheryEuropeVentSelect,
)


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


def _make_seat_select(key: str, data: CheryData):
    coordinator = SimpleNamespace(
        data=data,
        last_update_success=True,
        api=SimpleNamespace(send_command=AsyncMock(return_value={"ok": True})),
        async_set_updated_data=Mock(),
        schedule_refresh_after_command=Mock(),
    )
    entry = SimpleNamespace(entry_id="entry-1", options={CONF_PIN: "1234"})
    description = next(item for item in SEAT_SELECT_DESCRIPTIONS if item.key == key)
    select = CheryEuropeSeatSelect(coordinator, description, entry)
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


def test_seat_select_reports_reported_level():
    select, _ = _make_seat_select(
        "driver_seat_heating",
        CheryData(vin="VIN1", seat_levels={"driver_seat_heating": 2}),
    )
    assert select.current_option == "medium"


def test_seat_select_reports_off_for_zero_level():
    select, _ = _make_seat_select(
        "rear_left_seat_ventilation",
        CheryData(vin="VIN1", seat_levels={"rear_left_seat_ventilation": 0}),
    )
    assert select.current_option == "off"


def test_seat_select_without_levels_has_no_option():
    select, _ = _make_seat_select("passenger_seat_heating", CheryData(vin="VIN1"))
    assert select.current_option is None


def test_seat_select_offers_every_level():
    select, _ = _make_seat_select("driver_seat_ventilation", CheryData(vin="VIN1"))
    assert select.options == ["off", "low", "medium", "high"]


@pytest.mark.asyncio
async def test_seat_select_sends_chosen_level():
    select, coordinator = _make_seat_select("driver_seat_heating", CheryData(vin="VIN1"))

    await select.async_select_option("medium")

    coordinator.api.send_command.assert_awaited_once()
    call = coordinator.api.send_command.await_args
    assert call.args == ("VIN1", "ve_1204", "1234")
    assert call.kwargs["seat_field"] == "mSeatHeating"
    assert call.kwargs["enabled"] is True
    assert call.kwargs["level"] == 2


@pytest.mark.asyncio
async def test_seat_select_off_sends_disabled():
    select, coordinator = _make_seat_select(
        "rear_right_seat_ventilation", CheryData(vin="VIN1")
    )

    await select.async_select_option("off")

    call = coordinator.api.send_command.await_args
    assert call.kwargs["seat_field"] == "brSeatAiry"
    assert call.kwargs["enabled"] is False
    assert call.kwargs["level"] == 0


@pytest.mark.asyncio
async def test_setup_moves_seat_switches_to_selects():
    from custom_components.chery_europe.select import async_setup_entry

    coordinator = SimpleNamespace(
        data=CheryData(vin="VIN1"),
        api=SimpleNamespace(permissions={}),
        last_update_success=True,
    )
    entry = SimpleNamespace(entry_id="entry-1", runtime_data=coordinator, options={})
    added: list = []
    removed: list = []
    old_switch = SimpleNamespace(
        domain="switch",
        unique_id="entry-1_driver_seat_heating",
        entity_id="switch.driver_seat_heating",
    )
    new_select = SimpleNamespace(
        domain="select",
        unique_id="entry-1_driver_seat_heating_level_select",
        entity_id="select.driver_seat_heating",
    )
    registry = SimpleNamespace(
        async_get_entity_id=lambda domain, _platform, unique_id: f"{domain}.{unique_id}",
        async_remove=lambda entity_id: removed.append(entity_id),
    )

    with (
        patch("custom_components.chery_europe.entity.er.async_get", return_value=registry),
        patch(
            "custom_components.chery_europe.entity.er.async_entries_for_config_entry",
            return_value=[old_switch, new_select],
        ),
    ):
        await async_setup_entry(Mock(), entry, lambda entities: added.extend(entities))

    keys = {entity.entity_description.key for entity in added}
    assert "driver_seat_heating" in keys
    assert removed == ["switch.driver_seat_heating"]


@pytest.mark.asyncio
async def test_setup_omits_denied_seat_select():
    from custom_components.chery_europe.select import async_setup_entry

    coordinator = SimpleNamespace(
        data=CheryData(vin="VIN1"),
        api=SimpleNamespace(permissions={2147: 0, 20414: 0, 2148: 1}),
        last_update_success=True,
    )
    entry = SimpleNamespace(entry_id="entry-1", runtime_data=coordinator, options={})
    added: list = []
    removed: list = []
    registry = SimpleNamespace(
        async_get_entity_id=lambda domain, _platform, unique_id: f"{domain}.{unique_id}",
        async_remove=lambda entity_id: removed.append(entity_id),
    )

    with (
        patch("custom_components.chery_europe.entity.er.async_get", return_value=registry),
        patch(
            "custom_components.chery_europe.entity.er.async_entries_for_config_entry",
            return_value=[],
        ),
    ):
        await async_setup_entry(Mock(), entry, lambda entities: added.extend(entities))

    keys = {entity.entity_description.key for entity in added}
    assert "rear_left_seat_ventilation" not in keys
    assert "rear_right_seat_ventilation" in keys
    # the denied select is cleaned up under its own unique id, not the old one
    assert removed == ["select.entry-1_rear_left_seat_ventilation_level_select"]
