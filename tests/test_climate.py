# pyright: reportArgumentType=false, reportOptionalMemberAccess=false

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import HomeAssistantError

from custom_components.chery_europe.climate import (
    CLIMATE_COMMAND_ID,
    CLIMATE_DESCRIPTION,
    DEFAULT_TARGET_TEMPERATURE,
    CheryEuropeClimate,
)
from custom_components.chery_europe.const import (
    ATTR_COMMAND_ID,
    ATTR_PIN,
    ATTR_VIN,
    CONF_PIN,
    DOMAIN,
    SERVICE_SEND_COMMAND,
)
from custom_components.chery_europe.data import CheryData

PIN = "1234"
VIN = "VIN123456"


def _make_climate(vin: str = VIN, pin: str | None = PIN) -> CheryEuropeClimate:
    """Build a CheryEuropeClimate wired to a mocked hass/services layer."""
    data = CheryData(vin=vin)
    coordinator = SimpleNamespace(data=data, last_update_success=True)
    entry = SimpleNamespace(entry_id="entry-1", options={CONF_PIN: pin} if pin else {})
    climate = CheryEuropeClimate(coordinator, CLIMATE_DESCRIPTION, entry)

    hass = SimpleNamespace()
    hass.services = SimpleNamespace(async_call=AsyncMock())
    hass.states = SimpleNamespace(async_set=Mock())
    hass.loop = Mock()
    climate.hass = hass
    # async_write_ha_state touches hass internals we do not exercise here.
    climate.async_write_ha_state = Mock()  # type: ignore[assignment]
    return climate


def _service_data(climate: CheryEuropeClimate) -> dict:
    """Return the data dict passed to the send_command service call."""
    call = climate.hass.services.async_call.await_args
    assert call is not None, "send_command service was not called"
    # async_call(DOMAIN, SERVICE_SEND_COMMAND, data, blocking=True)
    assert call.args[0] == DOMAIN
    assert call.args[1] == SERVICE_SEND_COMMAND
    assert call.kwargs == {"blocking": True}
    return call.args[2]


@pytest.mark.asyncio
async def test_set_temperature_sends_temperature_and_enabled_true():
    climate = _make_climate()

    await climate.async_set_temperature(pin=PIN, temperature=22.0)

    data = _service_data(climate)
    assert data[ATTR_VIN] == VIN
    assert data[ATTR_COMMAND_ID] == CLIMATE_COMMAND_ID
    assert data[ATTR_PIN] == PIN
    assert data["temperature"] == 22.0
    assert data["enabled"] is True
    # hvac_mode is not part of a plain temperature set.
    assert "hvac_mode" not in data


@pytest.mark.asyncio
async def test_turn_on_sends_enabled_true_with_temperature_fallback():
    climate = _make_climate()

    await climate.async_turn_on(pin=PIN)

    data = _service_data(climate)
    assert data["enabled"] is True
    # No prior target temperature -> falls back to the default.
    assert data["temperature"] == float(DEFAULT_TARGET_TEMPERATURE)
    assert data[ATTR_PIN] == PIN


@pytest.mark.asyncio
async def test_turn_off_sends_enabled_false():
    climate = _make_climate()

    await climate.async_turn_off(pin=PIN)

    data = _service_data(climate)
    assert data["enabled"] is False
    assert data["temperature"] == float(DEFAULT_TARGET_TEMPERATURE)
    assert "hvac_mode" not in data


@pytest.mark.asyncio
async def test_set_hvac_mode_auto_sends_enabled_true_and_mode_string():
    climate = _make_climate()

    await climate.async_set_hvac_mode(HVACMode.AUTO, pin=PIN)

    data = _service_data(climate)
    assert data["enabled"] is True
    assert data["hvac_mode"] == "auto"
    assert data["temperature"] == float(DEFAULT_TARGET_TEMPERATURE)


@pytest.mark.asyncio
async def test_set_hvac_mode_heat_sends_enabled_true_and_mode_string():
    climate = _make_climate()

    await climate.async_set_hvac_mode(HVACMode.HEAT, pin=PIN)

    data = _service_data(climate)
    assert data["enabled"] is True
    assert data["hvac_mode"] == "heat"


@pytest.mark.asyncio
async def test_set_hvac_mode_off_sends_enabled_false():
    climate = _make_climate()

    await climate.async_set_hvac_mode(HVACMode.OFF, pin=PIN)

    data = _service_data(climate)
    assert data["enabled"] is False
    assert data["hvac_mode"] == "off"
    assert data["temperature"] == float(DEFAULT_TARGET_TEMPERATURE)


@pytest.mark.asyncio
async def test_set_hvac_mode_unsupported_raises():
    climate = _make_climate()

    with pytest.raises(HomeAssistantError):
        await climate.async_set_hvac_mode(HVACMode.COOL, pin=PIN)

    climate.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_hvac_mode_uses_stored_pin_from_options():
    climate = _make_climate()

    await climate.async_set_hvac_mode(HVACMode.AUTO)

    data = _service_data(climate)
    assert data[ATTR_PIN] == PIN


@pytest.mark.asyncio
async def test_set_temperature_requires_pin():
    climate = _make_climate(pin=None)

    with pytest.raises(HomeAssistantError):
        await climate.async_set_temperature(temperature=22.0)

    climate.hass.services.async_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_climate_command_requires_vin():
    climate = _make_climate(vin="")

    with pytest.raises(HomeAssistantError):
        await climate.async_turn_off(pin=PIN)

    climate.hass.services.async_call.assert_not_awaited()


def test_hvac_mode_shows_auto_when_api_enabled_even_if_local_mode_off():
    data = CheryData(vin=VIN, hvac_enabled=True)
    coordinator = SimpleNamespace(data=data, last_update_success=True)
    entry = SimpleNamespace(entry_id="entry-1", options={CONF_PIN: PIN})
    climate = CheryEuropeClimate(coordinator, CLIMATE_DESCRIPTION, entry)

    assert climate.hvac_mode == HVACMode.AUTO