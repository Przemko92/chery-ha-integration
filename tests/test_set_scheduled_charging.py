# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Tests for the set_scheduled_charging service."""

from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.chery_europe.const import (
    DOMAIN,
    SERVICE_SET_SCHEDULED_CHARGING,
)
from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.services import async_setup_services

VIN = "VIN123"
PIN = "4321"


class _FakeServiceRegistry:
    def __init__(self) -> None:
        self._handlers: dict = {}

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) in self._handlers

    def async_register(self, domain, service, handler, schema=None, supports_response=None) -> None:
        self._handlers[(domain, service)] = (handler, schema)

    async def async_call(self, domain, service, service_data=None, *, blocking=False, **kwargs):
        handler, schema = self._handlers[(domain, service)]
        data = schema(service_data) if schema is not None else (service_data or {})
        call = SimpleNamespace(data=data)
        return await handler(call)


def _make_hass():
    coordinator = SimpleNamespace(
        data=CheryData(vin=VIN),
        charge_start_minutes=480,
        charge_duration_hours=6,
        api=SimpleNamespace(send_command=AsyncMock(return_value={"ok": True})),
        async_set_updated_data=Mock(),
        schedule_refresh_after_command=Mock(),
    )
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


@pytest.mark.asyncio
async def test_set_scheduled_charging_sends_ve_1202():
    hass, coordinator = _make_hass()

    with patch(
        "custom_components.chery_europe.services.local_time_to_utc_minutes",
        return_value=1260,
    ) as convert:
        result = await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_SCHEDULED_CHARGING,
            {"start_time": "23:00:00", "duration_hours": 4},
            blocking=True,
        )

    convert.assert_called_once()
    coordinator.api.send_command.assert_awaited_once_with(
        VIN,
        "ve_1202",
        PIN,
        enabled=True,
        start_minutes=1260,
        duration_hours=4,
    )
    assert coordinator.charge_start_minutes == 1260
    assert coordinator.charge_duration_hours == 4
    assert result == {
        "success": True,
        "start_time": "23:00",
        "duration_hours": 4,
        "enabled": True,
    }


@pytest.mark.asyncio
async def test_set_scheduled_charging_can_disable():
    hass, coordinator = _make_hass()

    with patch(
        "custom_components.chery_europe.services.local_time_to_utc_minutes",
        return_value=480,
    ):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_SCHEDULED_CHARGING,
            {
                "start_time": time(8, 0),
                "duration_hours": 6,
                "enabled": False,
            },
            blocking=True,
        )

    call = coordinator.api.send_command.await_args
    assert call.kwargs["enabled"] is False
    assert call.kwargs["start_minutes"] == 480


@pytest.mark.asyncio
async def test_set_scheduled_charging_requires_pin():
    hass, coordinator = _make_hass()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    entry.options = {}

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_SCHEDULED_CHARGING,
            {"start_time": "22:00:00", "duration_hours": 3},
            blocking=True,
        )

    coordinator.api.send_command.assert_not_awaited()
