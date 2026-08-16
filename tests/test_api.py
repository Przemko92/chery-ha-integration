"""Tests for CheryEuropeApi request headers, refresh, retry, and metadata.

Covers plan T8 (identity/signing headers), T9 (command metadata), and T10
(401 refresh+retry, refresh failure, retry exhaustion).
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.api import MAX_RETRIES, CheryEuropeApi  # noqa: E402
from custom_components.chery_europe.exceptions import (  # noqa: E402
    CheryEuropeAuthError,
    CheryEuropeConnectionError,
)


class _Response:
    """Minimal async context manager mimicking an aiohttp response."""

    def __init__(self, status=200, payload=None):
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


def _auth():
    return SimpleNamespace(
        access_token="tok-abc",
        refresh_token_value="ref-xyz",
        expires_in=43200,
        token_obtained_at=None,
        needs_proactive_refresh=lambda quota=0.8: False,
    )


def _api(auth, session):
    api = CheryEuropeApi(auth, session)
    api._t_user_id = "429651957297274880"
    api._user_token = "ut-token"
    return api


_TSP_LOGIN_OK = (200, {"data": {"tUserId": "429651957297274880", "userToken": "ut"}})


class _Session:
    """Mock aiohttp session that records request() calls.

    Pass ``responses`` as a list of ``(status, payload)`` tuples for
    sequential responses (e.g. 401 then 200).  Without ``responses`` every
    call returns the same ``status``/``payload``.
    """

    def __init__(self, status=200, payload=None, responses=None):
        self.status = status
        self._payload = payload or {}
        self._responses = responses
        self._index = 0
        self.request_count = 0
        self.last_call = None
        self.calls = []

    def request(self, method, url, **kwargs):
        self.request_count += 1
        self.calls.append((method, url, kwargs))
        self.last_call = (method, url, kwargs)
        if self._responses is not None:
            if self._index < len(self._responses):
                status, payload = self._responses[self._index]
                self._index += 1
            else:
                status, payload = self._responses[-1]
        else:
            status, payload = self.status, self._payload
        return _Response(status, payload)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


_IDENTITY_HEADERS = (
    "signature",
    "nonce",
    "url",
    "timestamp",
    "agent",
    "version",
    "DEPT-ID",
    "TENANT-ID",
    "TENANT-CODE",
    "CLIENT-TOC",
)


@pytest.mark.asyncio
async def test_get_vehicle_status_uses_realtime_endpoint():
    """get_vehicle_status reads live telemetry from tspconsole realtime."""
    realtime_body = {
        "dumpEnergy": "72",
        "pureElectricRange": "60",
        "mileageSurplus": "215",
    }
    session = _Session(responses=[(200, {"code": "000000", "body": realtime_body})])
    api = _api(_auth(), session)

    result = await api.get_vehicle_status(vin="TESTVIN")

    assert result == realtime_body
    assert session.request_count == 1
    method, url, kwargs = session.last_call
    assert method == "POST"
    assert "/asr/manager/realtime" in url
    assert kwargs["headers"]["Authorization"] == "ut-token"
    body = json.loads(kwargs["data"])
    assert body["vin"] == "TESTVIN"
    assert body["appId"] == "eu-1"
    assert "sign" in body


@pytest.mark.asyncio
async def test_get_vehicle_status_asleep_returns_none():
    """Realtime code A07900 means the vehicle is asleep and has no live frame."""
    session = _Session(responses=[(200, {"code": "A07900"})])
    api = _api(_auth(), session)

    result = await api.get_vehicle_status(vin="TESTVIN")

    assert result is None


@pytest.mark.asyncio
async def test_get_vehicle_location_uses_query_endpoint():
    session = _Session(
        responses=[(200, {"code": "000000", "data": {"lat": "50.06", "lon": "19.93"}})]
    )
    api = _api(_auth(), session)

    result = await api.get_vehicle_location(vin="TESTVIN")

    assert result == {"lat": "50.06", "lon": "19.93"}
    method, url, kwargs = session.last_call
    assert "/asc/vehicleControl/queryVehicleLocation" in url
    assert json.loads(kwargs["data"])["vin"] == "TESTVIN"

    """get_vehicle_list (POST after TSP login) omits the `keys` header."""
    session = _Session(responses=[_TSP_LOGIN_OK, (200, {"data": []})])
    api = CheryEuropeApi(_auth(), session)

    await api.get_vehicle_list()

    assert session.request_count == 2
    method, url, kwargs = session.last_call
    assert method == "POST"
    assert "/api/tsp/v1/app/vmc/queryList" in url
    headers = kwargs["headers"]

    for header in _IDENTITY_HEADERS:
        assert header in headers, f"missing identity header: {header}"
    assert "keys" not in headers
    assert headers["Authorization"] == "Bearer tok-abc"
    assert kwargs["json"] == {
        "tUserId": "429651957297274880",
        "channelId": 5,
    }


@pytest.mark.asyncio
async def test_send_command_uses_air_control():
    """Climate commands go through tspconsole airControl with a minted taskId."""
    session = _Session(
        responses=[
            (200, {"code": "000000"}),
            (200, {"code": "000000", "data": {"taskId": "TASK123"}}),
            (200, {"code": "A00079"}),
        ]
    )
    api = _api(_auth(), session)

    result = await api.send_command(
        vin="VIN",
        command_id="ve_1104",
        pin="1234",
        temperature=22.0,
        enabled=True,
    )

    assert result["ok"] is True
    assert session.request_count == 3
    method, url, kwargs = session.last_call
    assert method == "POST"
    assert "/asc/vehicleControl/airControl" in url
    body = json.loads(kwargs["data"])
    assert body["airControlType"] == "1"
    assert body["temperature"] == "22.0"
    assert body["times"] == "15"
    assert body["taskId"] == "TASK123"
    assert body["vin"] == "VIN"


@pytest.mark.asyncio
async def test_send_command_uses_air_control_off():
    """Turning climate off sends airControlType 0 with the current temperature."""
    session = _Session(
        responses=[
            (200, {"code": "000000"}),
            (200, {"code": "000000", "data": {"taskId": "TASK123"}}),
            (200, {"code": "A00079"}),
        ]
    )
    api = _api(_auth(), session)

    result = await api.send_command(
        vin="VIN",
        command_id="ve_1104",
        pin="1234",
        temperature=22.0,
        enabled=False,
    )

    assert result["ok"] is True
    body = json.loads(session.last_call[2]["data"])
    assert body["airControlType"] == "0"
    assert body["temperature"] == "22.0"


@pytest.mark.asyncio
async def test_send_command_lock_uses_lock_control():
    """Lock commands map to lockControl with lockType derived from action."""
    session = _Session(
        responses=[
            (200, {"code": "000000"}),
            (200, {"code": "000000", "data": {"taskId": "TASK123"}}),
            (200, {"code": "A00079"}),
        ]
    )
    api = _api(_auth(), session)

    result = await api.send_command(
        vin="VIN",
        command_id="ve_1105",
        pin="1234",
        action="unlock",
    )

    assert result["ok"] is True
    body = json.loads(session.last_call[2]["data"])
    assert body["lockType"] == "1"


@pytest.mark.asyncio
async def test_send_command_rejects_invalid_pin():
    """checkPassword without taskId raises CheryEuropeAuthError."""
    session = _Session(
        responses=[
            (200, {"code": "000000"}),
            (200, {"code": "A00285", "msg": "password error"}),
        ]
    )
    api = _api(_auth(), session)

    with pytest.raises(CheryEuropeAuthError):
        await api.send_command(vin="VIN", command_id="ve_1104", pin="bad", enabled=True)


@pytest.mark.asyncio
async def test_api_401_triggers_refresh_and_retries():
    """401 on BFF requests triggers token refresh then retries."""
    session = _Session(responses=[(401, {}), (200, {"data": []})])
    auth = _auth()

    refresh_calls = []

    async def _refresh(refresh_token):
        refresh_calls.append(refresh_token)
        auth.access_token = "tok-refreshed"

    auth.refresh_token = _refresh
    api = _api(auth, session)

    result = await api.get_vehicle_list()

    assert result == []
    assert session.request_count == 2
    assert refresh_calls == ["ref-xyz"]
    _method, _url, kwargs = session.calls[1]
    assert kwargs["headers"]["Authorization"] == "Bearer tok-refreshed"


@pytest.mark.asyncio
async def test_api_401_refresh_failure_raises_auth_error():
    """401 with refresh failure raises CheryEuropeAuthError."""
    session = _Session(responses=[_TSP_LOGIN_OK, (401, {})])
    auth = _auth()

    async def _refresh_fail(refresh_token):
        raise CheryEuropeAuthError("Refresh token expired")

    auth.refresh_token = _refresh_fail
    api = CheryEuropeApi(auth, session)

    with pytest.raises(CheryEuropeAuthError):
        await api.get_vehicle_list()

    assert session.request_count == 2


@pytest.mark.asyncio
async def test_api_retry_exhaustion_raises_typed_error(monkeypatch):
    """500 on all retries raises CheryEuropeConnectionError."""
    session = _Session(
        responses=[
            _TSP_LOGIN_OK,
            (500, {"error": "server error"}),
            (500, {"error": "server error"}),
            (500, {"error": "server error"}),
        ]
    )
    api = CheryEuropeApi(_auth(), session)

    sleep_calls = []

    async def _fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    with pytest.raises(CheryEuropeConnectionError):
        await api.get_vehicle_list()

    assert session.request_count == 1 + MAX_RETRIES
    # Backoff is 2**attempt; sleep before retries 1 and 2, not before the last.
    assert sleep_calls == [1, 2]


@pytest.mark.asyncio
async def test_api_424_raises_auth_error_without_retry(monkeypatch):
    """424 means the session is dead; do not retry, force a fresh login."""
    session = _Session(responses=[_TSP_LOGIN_OK, (424, {"error": "failed dependency"})])
    api = CheryEuropeApi(_auth(), session)

    sleep_calls = []

    async def _fake_sleep(delay):
        sleep_calls.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    with pytest.raises(CheryEuropeAuthError):
        await api.get_vehicle_list()

    assert session.request_count == 2
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_api_401_persists_refreshed_tokens():
    """Successful 401 refresh must invoke the token persistence callback."""
    from custom_components.chery_europe.types.auth_models import AuthResponse

    session = _Session(responses=[(401, {}), (200, {"data": []})])
    auth = _auth()
    persisted = []

    async def _refresh(refresh_token):
        auth.access_token = "tok-refreshed"
        auth.refresh_token_value = "ref-new"
        return AuthResponse(
            access_token="tok-refreshed",
            refresh_token="ref-new",
            expires_in=43200,
            token_type="Bearer",
        )

    auth.refresh_token = _refresh
    api = _api(auth, session)
    api._on_tokens_updated = lambda response: persisted.append(response)

    await api.get_vehicle_list()

    assert len(persisted) == 1
    assert persisted[0].access_token == "tok-refreshed"
    assert persisted[0].refresh_token == "ref-new"


@pytest.mark.asyncio
async def test_concurrent_refresh_only_runs_once():
    """Parallel refreshes must not burn a rotated refresh_token."""
    from custom_components.chery_europe.types.auth_models import AuthResponse

    refresh_count = 0
    started = asyncio.Event()
    release = asyncio.Event()
    auth = _auth()
    auth.access_token = "tok-old"

    async def _refresh(refresh_token):
        nonlocal refresh_count
        refresh_count += 1
        started.set()
        await release.wait()
        auth.access_token = "tok-new"
        auth.refresh_token_value = "ref-new"
        return AuthResponse(
            access_token="tok-new",
            refresh_token="ref-new",
            expires_in=43200,
            token_type="Bearer",
        )

    auth.refresh_token = _refresh
    api = CheryEuropeApi(auth, _Session())

    first = asyncio.create_task(api._refresh_token(seen_access_token="tok-old"))
    await started.wait()
    second = asyncio.create_task(api._refresh_token(seen_access_token="tok-old"))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)

    assert refresh_count == 1
    assert auth.access_token == "tok-new"


@pytest.mark.asyncio
async def test_ensure_fresh_token_refreshes_when_near_expiry():
    """Proactive refresh runs when the access token is past the lifetime quota."""
    from custom_components.chery_europe.types.auth_models import AuthResponse

    auth = _auth()
    auth.needs_proactive_refresh = lambda quota=0.8: True
    refresh_calls = []

    async def _refresh(refresh_token):
        refresh_calls.append(refresh_token)
        auth.access_token = "tok-new"
        return AuthResponse(
            access_token="tok-new",
            refresh_token="ref-new",
            expires_in=43200,
            token_type="Bearer",
        )

    auth.refresh_token = _refresh
    api = CheryEuropeApi(auth, _Session())

    assert await api.ensure_fresh_token() is True
    assert refresh_calls == ["ref-xyz"]


@pytest.mark.asyncio
async def test_ensure_fresh_token_skips_when_not_needed():
    auth = _auth()
    auth.needs_proactive_refresh = lambda quota=0.8: False
    api = CheryEuropeApi(auth, _Session())

    assert await api.ensure_fresh_token() is False

