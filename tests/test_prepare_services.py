# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Tests for the scheduled preparation services."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.chery_europe.const import (
    DOMAIN,
    SERVICE_CANCEL_PREPARE_PLAN,
    SERVICE_LIST_PREPARE_PLANS,
    SERVICE_SET_PREPARE_PLAN,
)
from custom_components.chery_europe.data import (
    CheryData,
    apply_travel_appointment,
    parse_travel_appointment,
)
from custom_components.chery_europe.prepare_plan import build_plan
from custom_components.chery_europe.services import async_setup_services

VIN = "VIN123"
PIN = "4321"


class _FakeServiceRegistry:
    def __init__(self) -> None:
        self._handlers: dict = {}

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) in self._handlers

    def async_register(
        self, domain, service, handler, schema=None, supports_response=None
    ) -> None:
        self._handlers[(domain, service)] = (handler, schema)

    async def async_call(
        self, domain, service, service_data=None, *, blocking=False, **kwargs
    ):
        handler, schema = self._handlers[(domain, service)]
        data = schema(service_data) if schema is not None else (service_data or {})
        return await handler(SimpleNamespace(data=data))


def _make_hass(plans=None):
    api = SimpleNamespace(
        send_travel_appointment=AsyncMock(return_value={"ok": True, "code": "000000"}),
        query_travel_appointment=AsyncMock(return_value=plans or []),
    )
    coordinator = SimpleNamespace(
        data=CheryData(vin=VIN, prepare_plans=plans),
        api=api,
        permissions={},
        _permissions_loaded=False,
        invalidate_prepare_cache=Mock(),
        schedule_refresh_after_command=Mock(),
    )

    def _store(data):
        coordinator.data = data

    coordinator.async_set_updated_data = Mock(side_effect=_store)
    entry = SimpleNamespace(
        entry_id="entry-1",
        runtime_data=coordinator,
        options={"pin": PIN},
    )
    hass = SimpleNamespace(
        services=_FakeServiceRegistry(),
        config_entries=SimpleNamespace(async_entries=lambda _domain: [entry]),
    )
    async_setup_services(hass)
    return hass, coordinator


def _sent_plans(coordinator) -> list[dict]:
    args = coordinator.api.send_travel_appointment.await_args
    return args.args[2]


@pytest.mark.asyncio
async def test_set_prepare_plan_sends_the_whole_plan_list():
    hass, coordinator = _make_hass(plans=[])

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_PREPARE_PLAN,
        {
            "plan_name": "Work",
            "travel_time": "07:30",
            "repeat": "workdays",
            "temperature": 22,
            "battery_heat": True,
            "front_defrost": True,
        },
        blocking=True,
    )

    plans = _sent_plans(coordinator)
    assert len(plans) == 1
    plan = plans[0]
    assert plan["name"] == "Work"
    assert plan["travel_time"] == "07:30"
    assert plan["days"] == [1, 2, 3, 4, 5]
    assert plan["temperature"] == "22.0"
    assert plan["features"]["battery_heat"] is True
    assert plan["features"]["front_defrost"] is True
    assert result["success"] is True
    # The coordinator mirrors the new list straight away.
    coordinator.async_set_updated_data.assert_called_once()
    coordinator.invalidate_prepare_cache.assert_called_once()
    coordinator.schedule_refresh_after_command.assert_called_once()


@pytest.mark.asyncio
async def test_set_prepare_plan_keeps_existing_plans():
    existing = build_plan(
        name="Gym", travel_time="18:00", plan_id="42", enabled=True
    )
    hass, coordinator = _make_hass(plans=[existing])

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_PREPARE_PLAN,
        {"plan_name": "Work", "travel_time": "07:30"},
        blocking=True,
    )

    plans = _sent_plans(coordinator)
    assert [plan["name"] for plan in plans] == ["Gym", "Work"]


@pytest.mark.asyncio
async def test_set_prepare_plan_edits_a_plan_by_id():
    existing = build_plan(name="Work", travel_time="07:30", plan_id="42")
    hass, coordinator = _make_hass(plans=[existing])

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_PREPARE_PLAN,
        {
            "plan_id": "42",
            "plan_name": "Work",
            "travel_time": "08:15",
            "steering_wheel_heat": True,
        },
        blocking=True,
    )

    plans = _sent_plans(coordinator)
    assert len(plans) == 1
    assert plans[0]["travel_time"] == "08:15"
    assert plans[0]["features"]["steering_wheel_heat"] is True


@pytest.mark.asyncio
async def test_set_prepare_plan_dry_run_does_not_touch_the_car():
    hass, coordinator = _make_hass(plans=[])

    result = await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_PREPARE_PLAN,
        {
            "plan_name": "Work",
            "travel_time": "07:30",
            "temperature": 21,
            "battery_heat": True,
            "dry_run": True,
        },
        blocking=True,
    )

    coordinator.api.send_travel_appointment.assert_not_awaited()
    assert result["dry_run"] is True
    body = result["body"]
    plan = body["appointmentTravelAOS"][0]
    assert plan["travelTime"] == "450"
    assert plan["switcher"] == "1"
    assert plan["id"] is None
    assert plan["planId"] is None
    assert "appointmentTravelSetVOS" not in body
    assert body["mainSwitcher"] == "1"


@pytest.mark.asyncio
async def test_set_prepare_plan_refuses_to_write_before_the_list_is_known():
    hass, coordinator = _make_hass()

    with pytest.raises(HomeAssistantError, match="unknown"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_PREPARE_PLAN,
            {"plan_name": "Work", "travel_time": "07:30"},
            blocking=True,
        )

    coordinator.api.send_travel_appointment.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_prepare_plan_rejects_a_duplicate_name():
    existing = build_plan(name="Work", travel_time="07:30", plan_id="42")
    hass, coordinator = _make_hass(plans=[existing])

    with pytest.raises(HomeAssistantError, match="already exists"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_PREPARE_PLAN,
            {"plan_name": "Work", "travel_time": "12:00"},
            blocking=True,
        )

    coordinator.api.send_travel_appointment.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_prepare_plan_rejects_a_name_over_ten_characters():
    hass, _ = _make_hass(plans=[])

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_PREPARE_PLAN,
            {"plan_name": "Bardzo dluga nazwa", "travel_time": "07:30"},
            blocking=True,
        )


@pytest.mark.asyncio
async def test_cancel_prepare_plan_switches_the_plan_off():
    existing = build_plan(
        name="Work", travel_time="07:30", plan_id="42", battery_heat=True
    )
    hass, coordinator = _make_hass(plans=[existing])

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CANCEL_PREPARE_PLAN,
        {"plan_id": "42"},
        blocking=True,
    )

    plans = _sent_plans(coordinator)
    assert plans[0]["enabled"] is False
    assert plans[0]["features"]["battery_heat"] is False


@pytest.mark.asyncio
async def test_cancel_prepare_plan_unknown_id_raises():
    hass, coordinator = _make_hass(plans=[])

    with pytest.raises(HomeAssistantError, match="Unknown plan_id"):
        await hass.services.async_call(
            DOMAIN, SERVICE_CANCEL_PREPARE_PLAN, {"plan_id": "9"}, blocking=True
        )

    coordinator.api.send_travel_appointment.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_prepare_plans_returns_the_car_plans():
    payload = {
        "code": "000000",
        "data": {
            "preparePlans": [
                {"planId": "abc", "planName": "Work", "travelTime": "07:30",
                 "cycleData": [1, 2, 3, 4, 5], "switchStatus": 1}
            ]
        },
    }
    hass, _coordinator = _make_hass(plans=parse_travel_appointment(payload))

    result = await hass.services.async_call(
        DOMAIN, SERVICE_LIST_PREPARE_PLANS, {}, blocking=True
    )

    assert result["success"] is True
    assert [plan["name"] for plan in result["plans"]] == ["Work"]
    assert result["next_departure"] is not None


@pytest.mark.asyncio
async def test_list_prepare_plans_reports_a_failed_query():
    hass, coordinator = _make_hass(plans=[])
    coordinator.api.query_travel_appointment = AsyncMock(return_value=None)

    result = await hass.services.async_call(
        DOMAIN, SERVICE_LIST_PREPARE_PLANS, {}, blocking=True
    )

    assert result["success"] is False
    assert "did not return" in result["message"]


def test_apply_travel_appointment_uses_the_home_assistant_timezone():
    from datetime import UTC

    from homeassistant.util import dt as dt_util

    zone = dt_util.get_time_zone("Europe/Warsaw")
    assert zone is not None
    dt_util.set_default_time_zone(zone)
    try:
        plan = build_plan(name="Work", travel_time="07:30")
        data = apply_travel_appointment(CheryData(vin=VIN), [plan])
        upcoming = dt_util.parse_datetime(data.prepare_next_departure)
        assert upcoming is not None
        local = dt_util.as_local(upcoming)
        assert (local.hour, local.minute) == (7, 30)
    finally:
        dt_util.set_default_time_zone(UTC)


def test_empty_travel_poll_keeps_a_known_plan_list():
    import asyncio
    from types import SimpleNamespace

    from custom_components.chery_europe.coordinator import (
        CheryEuropeDataUpdateCoordinator,
    )

    coordinator = object.__new__(CheryEuropeDataUpdateCoordinator)
    coordinator._prepare_polled_at = None

    async def query(_vin):
        return []

    coordinator.api = SimpleNamespace(query_travel_appointment=query)
    plans = [build_plan(name="Work", travel_time="07:30")]
    updated = asyncio.run(
        coordinator._merge_travel_appointment(CheryData(vin=VIN, prepare_plans=plans))
    )

    assert updated.prepare_plans == plans
    assert coordinator._prepare_polled_at is not None


def test_apply_travel_appointment_keeps_plans_when_payload_is_empty():
    plan = build_plan(name="Work", travel_time="07:30")
    data = apply_travel_appointment(CheryData(vin=VIN), [plan])
    assert data.prepare_next_departure is not None

    kept = apply_travel_appointment(data, None)
    assert kept is data
    assert kept.prepare_plans is not None and len(kept.prepare_plans) == 1
    assert kept.prepare_next_departure == data.prepare_next_departure


def test_apply_travel_appointment_replaces_the_list():
    data = CheryData(vin=VIN, prepare_plans=[build_plan(name="Work", travel_time="07:30")])
    new = [build_plan(name="Gym", travel_time="18:00", enabled=False)]

    updated = apply_travel_appointment(data, new, polled_at="2026-11-23T08:00:00+00:00")

    assert updated.prepare_plans is not None
    assert [plan["name"] for plan in updated.prepare_plans] == ["Gym"]
    assert updated.prepare_next_departure is None
    assert updated.prepare_polled_at == "2026-11-23T08:00:00+00:00"


def _prepare_sensor(key: str, data):
    from custom_components.chery_europe.sensor import (
        PREPARE_SENSOR_DESCRIPTIONS,
        CheryEuropePrepareSensor,
    )

    description = next(
        item for item in PREPARE_SENSOR_DESCRIPTIONS if item.key == key
    )
    sensor = object.__new__(CheryEuropePrepareSensor)
    sensor.entity_description = description
    sensor.coordinator = SimpleNamespace(data=data, last_update_success=True)
    return sensor


def test_prepare_plans_sensor_counts_only_enabled_plans():
    plans = [
        build_plan(
            name="Work", travel_time="07:30", plan_id="1", battery_heat=True
        ),
        build_plan(name="Gym", travel_time="18:00", plan_id="2", enabled=False),
    ]
    data = apply_travel_appointment(CheryData(vin=VIN), plans)

    sensor = _prepare_sensor("prepare_plans", data)

    assert sensor.native_value == 1
    attributes = sensor.extra_state_attributes
    assert [plan["name"] for plan in attributes["plans"]] == ["Work", "Gym"]
    # Only the features that are on are listed, to keep the attributes short.
    assert attributes["plans"][0]["battery_heat"] is True
    assert "front_defrost" not in attributes["plans"][0]


def test_next_departure_sensor_returns_a_datetime():
    from homeassistant.util import dt as dt_util

    plan = build_plan(name="Work", travel_time="07:30", plan_id="1")
    data = apply_travel_appointment(CheryData(vin=VIN), [plan])

    sensor = _prepare_sensor("prepare_next_departure", data)

    assert isinstance(sensor.native_value, datetime)
    assert sensor.native_value == dt_util.parse_datetime(data.prepare_next_departure)


def test_prepare_sensors_are_unknown_without_data():
    data = CheryData(vin=VIN)
    assert _prepare_sensor("prepare_plans", data).native_value is None
    assert _prepare_sensor("prepare_next_departure", data).native_value is None
