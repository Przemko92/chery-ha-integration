# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Tests for Chery Europe charging switches."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.switch import (
    CheryEuropeChargeSwitch,
    CheryEuropeScheduledChargeSwitch,
)

VIN = "VIN123456"


def _coordinator(data: CheryData | None = None):
    return SimpleNamespace(
        data=data or CheryData(vin=VIN),
        last_update_success=True,
        charge_start_minutes=480,
        charge_duration_hours=6,
        api=SimpleNamespace(send_command=AsyncMock(return_value={"ok": True})),
        async_set_updated_data=lambda data: None,
        schedule_refresh_after_command=lambda: None,
    )


def _entry():
    return SimpleNamespace(entry_id="entry-1", options={"pin": "1234"})


def test_scheduled_charge_switch_reads_vehicle_plan():
    switch = CheryEuropeScheduledChargeSwitch(
        _coordinator(
            CheryData(
                vin=VIN,
                scheduled_charge_enabled=True,
                charge_appoint_plan={
                    "startTime": 465,
                    "timeConsuming": 360,
                    "cycleData": [1, 2, 3, 4, 5, 6, 7],
                },
            )
        ),
        _entry(),
    )

    assert switch.is_on is True
    attrs = switch.extra_state_attributes
    assert attrs is not None
    assert attrs["vehicle_start_time"] == "07:45"
    assert attrs["vehicle_duration_hours"] == 6.0


@pytest.mark.asyncio
async def test_scheduled_charge_turn_on_sends_plan():
    coordinator = _coordinator(CheryData(vin=VIN))
    switch = CheryEuropeScheduledChargeSwitch(coordinator, _entry())
    switch.async_write_ha_state = lambda: None

    await switch.async_turn_on()

    coordinator.api.send_command.assert_awaited_once_with(
        VIN,
        "ve_1202",
        "1234",
        enabled=True,
        start_minutes=480,
        duration_hours=6,
    )


@pytest.mark.asyncio
async def test_charge_switch_turn_on_sends_start_command():
    coordinator = _coordinator(CheryData(vin=VIN))
    switch = CheryEuropeChargeSwitch(coordinator, _entry())
    switch.async_write_ha_state = lambda: None

    await switch.async_turn_on()

    coordinator.api.send_command.assert_awaited_once_with(
        VIN,
        "ve_1201",
        "1234",
        enabled=True,
    )


def test_charge_entities_have_entity_descriptions():
    """Newer HA requires entity_description; unique_id must not collide with binary_sensor.charging."""
    charge = CheryEuropeChargeSwitch(_coordinator(), _entry())
    scheduled = CheryEuropeScheduledChargeSwitch(_coordinator(), _entry())

    assert charge.entity_description is not None
    assert charge.entity_description.device_class is None
    assert charge.entity_description.translation_placeholders is None
    assert charge.unique_id == f"{VIN}_charging_switch"

    assert scheduled.entity_description is not None
    assert scheduled.unique_id == f"{VIN}_scheduled_charging"
