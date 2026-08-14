# pyright: reportArgumentType=false

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.api import CheryEuropeApi
from custom_components.chery_europe.coordinator import CheryEuropeDataUpdateCoordinator
from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.diagnostics import REDACTED, _redact
from custom_components.chery_europe.exceptions import CheryEuropeRateLimitError


class _Response:
    def __init__(self, status, payload=None):
        self.status = status
        self._payload = payload or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return str(self._payload)


class _Session:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.request_count = 0

    def request(self, *args, **kwargs):
        self.request_count += 1
        status = self.statuses.pop(0)
        return _Response(status, {"ok": True})


def _coordinator(api):
    with patch("custom_components.chery_europe.coordinator.DataUpdateCoordinator.__init__", return_value=None):
        return CheryEuropeDataUpdateCoordinator(
            SimpleNamespace(),
            api,
            SimpleNamespace(options={}),
            scan_interval=None,
        )


@pytest.mark.asyncio
async def test_empty_vehicle_list_returns_empty_chery_data():
    api = SimpleNamespace(get_vehicle_list=AsyncMock(return_value=[]))
    data = await _coordinator(api)._async_update_data()

    assert data == CheryData()


def test_missing_fields_in_api_response_are_normalized_to_none():
    data = CheryData.from_api_response({"vin": "VIN123", "batteryLevel": "not-a-number"})

    assert data.vin == "VIN123"
    assert data.battery_level is None
    assert data.range_km is None
    assert data.tire_pressures is None


@pytest.mark.asyncio
async def test_500_error_is_retried_before_success():
    session = _Session([500, 500, 200])
    auth = SimpleNamespace(access_token="token", refresh_token_value="refresh")
    api = CheryEuropeApi(auth, session)

    with patch("custom_components.chery_europe.api.asyncio.sleep", new=AsyncMock()) as sleep:
        result = await api._request("GET", "/vehicles")

    assert result == {"ok": True}
    assert session.request_count == 3
    assert sleep.await_count == 2


@pytest.mark.asyncio
async def test_429_rate_limit_raises_after_retries():
    session = _Session([429, 429, 429])
    auth = SimpleNamespace(access_token="token", refresh_token_value="refresh")
    api = CheryEuropeApi(auth, session)

    with patch("custom_components.chery_europe.api.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(CheryEuropeRateLimitError):
            await api._request("GET", "/vehicles")

    assert session.request_count == 3


def test_diagnostics_redaction_removes_sensitive_nested_values():
    redacted = _redact(
        {
            "access_token": "secret",
            "refresh_token": "refresh",
            "vehicle": {"vin": "VIN123", "latitude": 50.0, "longitude": 20.0},
            "safe": "visible",
        }
    )

    assert redacted["access_token"] == REDACTED
    assert redacted["refresh_token"] == REDACTED
    assert redacted["vehicle"]["vin"] == REDACTED
    assert redacted["vehicle"]["latitude"] == REDACTED
    assert redacted["vehicle"]["longitude"] == REDACTED
    assert redacted["safe"] == "visible"
