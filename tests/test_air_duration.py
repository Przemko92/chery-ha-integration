# pyright: reportArgumentType=false, reportOptionalMemberAccess=false

"""Tests for the air-conditioning runtime (airControl ``times``) support."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol

pytest.importorskip("homeassistant")

from custom_components.chery_europe.climate import (
    CLIMATE_COMMAND_ID,
    CLIMATE_DESCRIPTION,
    CheryEuropeClimate,
)
from custom_components.chery_europe.const import (
    ATTR_AIR_DURATION,
    ATTR_COMMAND_ID,
    ATTR_PIN,
    CONF_PIN,
    DOMAIN,
    SERVICE_SEND_COMMAND,
)
from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.select import (
    AIR_DURATION_DESCRIPTION,
    AIR_DURATION_UNIQUE_SUFFIX,
    CheryEuropeAirDurationSelect,
)
from custom_components.chery_europe.services import SEND_COMMAND_SCHEMA
from custom_components.chery_europe.vehicle_commands import (
    AIR_DURATION_OPTIONS,
    DEFAULT_AIR_DURATION,
    build_air_control_body,
)

PIN = "1234"
VIN = "VIN123456"


def _make_select(duration: str = DEFAULT_AIR_DURATION) -> CheryEuropeAirDurationSelect:
    """Build the runtime select on a coordinator stub."""
    coordinator = SimpleNamespace(
        data=CheryData(vin=VIN),
        last_update_success=True,
        hvac_duration=duration,
        async_set_updated_data=Mock(),
        schedule_refresh_after_command=Mock(),
    )
    entry = SimpleNamespace(entry_id="entry-1", options={CONF_PIN: PIN})
    select = CheryEuropeAirDurationSelect(coordinator, AIR_DURATION_DESCRIPTION, entry)
    select.hass = SimpleNamespace()
    select.async_write_ha_state = Mock()  # type: ignore[assignment]
    return select


def _make_climate(duration: str | None = None) -> CheryEuropeClimate:
    """Build the climate entity whose coordinator carries a runtime choice."""
    coordinator = SimpleNamespace(
        data=CheryData(vin=VIN), last_update_success=True
    )
    if duration is not None:
        coordinator.hvac_duration = duration
    entry = SimpleNamespace(entry_id="entry-1", options={CONF_PIN: PIN})
    climate = CheryEuropeClimate(coordinator, CLIMATE_DESCRIPTION, entry)
    hass = SimpleNamespace()
    hass.services = SimpleNamespace(async_call=AsyncMock())
    hass.states = SimpleNamespace(async_set=Mock())
    hass.loop = Mock()
    climate.hass = hass
    climate.async_write_ha_state = Mock()  # type: ignore[assignment]
    return climate


def test_air_duration_options_match_the_app_choices():
    assert AIR_DURATION_OPTIONS == ("5", "10", "15")


def test_build_air_control_body_uses_the_selected_duration():
    body = build_air_control_body({"enabled": True, "duration": "10"})

    assert body["times"] == "10"


def test_build_air_control_body_falls_back_when_duration_is_missing():
    assert build_air_control_body({"enabled": True})["times"] == DEFAULT_AIR_DURATION
    assert (
        build_air_control_body({"enabled": True, "duration": None})["times"]
        == DEFAULT_AIR_DURATION
    )


def test_select_options_are_the_supported_durations():
    assert _make_select().options == ["5", "10", "15"]


def test_select_reports_the_coordinator_choice():
    select = _make_select("10")

    assert select.current_option == "10"
    assert select.unique_id.endswith(AIR_DURATION_UNIQUE_SUFFIX)


@pytest.mark.asyncio
async def test_select_stores_the_chosen_duration():
    select = _make_select("15")

    await select.async_select_option("5")

    assert select.coordinator.hvac_duration == "5"
    assert select.async_write_ha_state.called


@pytest.mark.asyncio
async def test_select_rejects_an_unsupported_duration():
    select = _make_select("15")

    with pytest.raises(ValueError):
        await select.async_select_option("7")

    assert select.coordinator.hvac_duration == "15"


@pytest.mark.asyncio
async def test_climate_start_sends_the_selected_duration():
    climate = _make_climate("5")

    await climate.async_turn_on()

    data = climate.hass.services.async_call.await_args.args[2]
    assert climate.hass.services.async_call.await_args.args[:2] == (
        DOMAIN,
        SERVICE_SEND_COMMAND,
    )
    assert data[ATTR_COMMAND_ID] == CLIMATE_COMMAND_ID
    assert data[ATTR_PIN] == PIN
    assert data[ATTR_AIR_DURATION] == "5"


@pytest.mark.asyncio
async def test_climate_start_falls_back_to_the_default_duration():
    climate = _make_climate()

    await climate.async_turn_on()

    data = climate.hass.services.async_call.await_args.args[2]
    assert data[ATTR_AIR_DURATION] == DEFAULT_AIR_DURATION


def test_send_command_schema_accepts_a_duration():
    result = SEND_COMMAND_SCHEMA(
        {"vin": VIN, "command_id": CLIMATE_COMMAND_ID, ATTR_AIR_DURATION: 10}
    )

    assert result[ATTR_AIR_DURATION] == "10"


def test_send_command_schema_rejects_an_unknown_duration():
    with pytest.raises(vol.Invalid):
        SEND_COMMAND_SCHEMA(
            {"vin": VIN, "command_id": CLIMATE_COMMAND_ID, ATTR_AIR_DURATION: "7"}
        )
