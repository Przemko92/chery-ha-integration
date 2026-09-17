# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Tests for the Chery Europe switch entity feedback state and PIN guard.

Verifies that ``is_on`` reads from ``CheryData.front_windshield_heating``
via ``_feedback_state``, that ``assumed_state`` is ``True`` when feedback is
absent (``None``), and that ``async_turn_on`` raises ``HomeAssistantError``
when no PIN is supplied.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.switch import (
    SWITCH_DESCRIPTIONS,
    CheryEuropeCommandSwitch,
)

VIN = "VIN123456"


def _description(key: str):
    """Return the switch entity description with the matching key."""
    for desc in SWITCH_DESCRIPTIONS:
        if desc.key == key:
            return desc
    raise KeyError(key)


def _make_switch(
    data: CheryData,
    key: str = "front_windshield_heating",
) -> CheryEuropeCommandSwitch:
    """Build a CheryEuropeCommandSwitch wired to a stub coordinator."""
    coordinator = SimpleNamespace(
        data=data,
        last_update_success=True,
        api=SimpleNamespace(send_command=AsyncMock()),
        async_request_refresh=AsyncMock(),
    )
    entry = SimpleNamespace(entry_id="entry-1", options={"pin": "1234"})
    return CheryEuropeCommandSwitch(coordinator, _description(key), entry)


def test_front_windshield_heating_on():
    """front_windshield_heating=True -> is_on is True."""
    switch = _make_switch(CheryData(vin=VIN, front_windshield_heating=True))
    assert switch.is_on is True


def test_front_windshield_defrost_reads_its_own_field():
    """front_windshield_defrost has its own feedback field."""
    switch = _make_switch(
        CheryData(vin=VIN, front_windshield_heating=False, front_windshield_defrost=True),
        key="front_windshield_defrost",
    )
    assert switch.is_on is True


@pytest.mark.asyncio
async def test_front_windshield_defrost_sends_climate_target():
    """ve_1108 rides on airControl and carries the current climate target."""
    switch = _make_switch(
        CheryData(vin=VIN, target_temperature=23.0), key="front_windshield_defrost"
    )
    switch.coordinator.api.send_command.return_value = {"ok": True}
    switch.coordinator.async_set_updated_data = lambda data: None
    switch.coordinator.schedule_refresh_after_command = lambda: None

    await switch.async_turn_on()

    switch.coordinator.api.send_command.assert_awaited_once_with(
        VIN, "ve_1108", "1234", enabled=True, temperature=23.0
    )


def test_no_feedback_assumed_state():
    """No feedback fields -> is_on is None and assumed_state is True."""
    switch = _make_switch(CheryData(vin=VIN))
    assert switch.is_on is None
    assert switch.assumed_state is True


@pytest.mark.asyncio
async def test_turn_on_requires_pin():
    """async_turn_on without PIN raises HomeAssistantError before any API call."""
    switch = _make_switch(CheryData(vin=VIN))
    switch._entry = SimpleNamespace(entry_id="entry-1", options={})

    with pytest.raises(HomeAssistantError):
        await switch.async_turn_on()

    switch.coordinator.api.send_command.assert_not_awaited()