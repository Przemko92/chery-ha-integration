# pyright: reportArgumentType=false, reportOptionalSubscript=false
"""Tests for the Chery Europe lock entity action passthrough.

Verifies that ``async_lock``/``async_unlock`` flow the ``action`` field all the
way through the ``send_command`` service to ``coordinator.api.send_command``
with ``command_id="ve_1105"`` and the PIN from the service call, without ever
storing the PIN.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.lock import LOCK_COMMAND_ID, LOCK_DESCRIPTION, CheryEuropeLock
from custom_components.chery_europe.services import async_setup_services

VIN = "VIN123"
PIN = "1234"


class _FakeServiceRegistry:
    """Minimal HA services registry that routes ``async_call`` to the real handler."""

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


def _make_lock():
    """Build a CheryEuropeLock wired to a real send_command service handler."""
    coordinator = SimpleNamespace(
        data=CheryData(vin=VIN, is_locked=True),
        last_update_success=True,
        api=SimpleNamespace(
            send_command=AsyncMock(return_value={"ok": True}),
        ),
        async_request_refresh=AsyncMock(),
        async_set_updated_data=Mock(),
        schedule_refresh_after_command=Mock(),
    )
    entry = SimpleNamespace(entry_id="entry-1", runtime_data=coordinator, options={})
    hass = SimpleNamespace(
        services=_FakeServiceRegistry(),
        config_entries=SimpleNamespace(async_entries=lambda _domain: [entry]),
    )
    # Register the real send_command service so the lock's service call reaches
    # coordinator.api.send_command exactly as in production.
    async_setup_services(hass)

    lock = CheryEuropeLock(coordinator, LOCK_DESCRIPTION, entry)
    lock.hass = hass
    return lock, coordinator


@pytest.mark.asyncio
async def test_async_unlock_sends_unlock_action_with_pin():
    """async_unlock flows action='unlock' through the service to api.send_command."""
    lock, coordinator = _make_lock()

    # HA entity services pass validated service data as keyword args.
    await lock.async_unlock(code=PIN)

    coordinator.api.send_command.assert_awaited_once()
    call = coordinator.api.send_command.await_args
    # Positional: vin, command_id, pin — command_id must stay ve_1105.
    assert call.args == (VIN, LOCK_COMMAND_ID, PIN)
    assert call.kwargs["action"] == "unlock"
    coordinator.async_request_refresh.assert_not_awaited()
    coordinator.schedule_refresh_after_command.assert_called_once()


@pytest.mark.asyncio
async def test_async_lock_sends_lock_action_with_pin():
    """async_lock flows action='lock' through the service to api.send_command."""
    lock, coordinator = _make_lock()

    await lock.async_lock(pin=PIN)

    coordinator.api.send_command.assert_awaited_once()
    call = coordinator.api.send_command.await_args
    assert call.args == (VIN, LOCK_COMMAND_ID, PIN)
    assert call.kwargs["action"] == "lock"
    coordinator.async_request_refresh.assert_not_awaited()
    coordinator.schedule_refresh_after_command.assert_called_once()


@pytest.mark.asyncio
async def test_async_unlock_without_pin_raises_homeassistant_error():
    """Missing PIN/code must raise HomeAssistantError before any service call."""
    lock, coordinator = _make_lock()

    with pytest.raises(HomeAssistantError):
        await lock.async_unlock()

    coordinator.api.send_command.assert_not_awaited()