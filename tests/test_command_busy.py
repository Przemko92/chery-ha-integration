"""The car runs one command at a time: A00082 is explained and retried.

Covers the readable code map and the busy retry inside ``send_command``.
"""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.api import CheryEuropeApi
from custom_components.chery_europe.const import COMMAND_BUSY_RETRY_DELAYS
from custom_components.chery_europe.error_codes import describe_code
from custom_components.chery_europe.request_queue import ApiRequestQueue
from custom_components.chery_europe.vehicle_commands import command_result


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
        return json.dumps(self._payload)


class _Session:
    """Mock aiohttp session returning queued ``(status, payload)`` responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.request_count = 0

    def request(self, method, url, **kwargs):
        status, payload = (
            self._responses[self.request_count]
            if self.request_count < len(self._responses)
            else (200, {})
        )
        self.request_count += 1
        return _Response(status, payload)

    def post(self, url, **kwargs):
        """tspconsole calls go through session.post."""
        return self.request("POST", url, **kwargs)


_AUTH = SimpleNamespace(
    access_token="tok-abc",
    refresh_token_value="ref-xyz",
    expires_in=43200,
    token_obtained_at=None,
    needs_proactive_refresh=lambda quota=0.8: False,
)


def _api(session):
    api = CheryEuropeApi(_AUTH, session)
    api._t_user_id = "429651957297274880"
    api._user_token = "ut-token"
    # No spacing between commands: the retry pause is what the tests drive.
    api._request_queue = ApiRequestQueue(min_interval=0)
    return api


def _task_id_calls():
    return [(200, {"code": "000000"}), (200, {"code": "000000", "data": {"taskId": "T1"}})]


def test_known_codes_are_explained():
    """The busy code says what happened instead of showing a bare code."""
    assert "zajęte" in describe_code("A00082")
    assert describe_code("A00084")
    assert describe_code(None) is None
    assert describe_code("X99999") is None


def test_command_result_explains_a_silent_refusal():
    """A refusal without msg gets the readable text; a backend msg wins."""
    silent = command_result({"code": "A00082"})
    assert silent["ok"] is False
    assert silent["message"] == describe_code("A00082")

    spoken = command_result({"code": "A00082", "msg": "vehicle busy"})
    assert spoken["message"] == "vehicle busy"

    unknown = command_result({"code": "X99999"})
    assert unknown["message"] is None


@pytest.mark.asyncio
async def test_busy_command_is_retried_once_and_then_succeeds():
    """A car busy refusal is not surfaced: the same command is sent again."""
    session = _Session([*_task_id_calls(), (200, {"code": "A00082"}), (200, {"code": "A00079"})])
    api = _api(session)
    sleeps = []

    async def _sleep(delay):
        sleeps.append(delay)

    api._sleep = _sleep

    result = await api.send_command(
        vin="VIN",
        command_id="ve_1202",
        pin="1234",
        enabled=True,
        start_minutes=180,
        duration_hours=6,
    )

    assert result["ok"] is True
    assert sleeps == [COMMAND_BUSY_RETRY_DELAYS[0]]
    assert session.request_count == 4


@pytest.mark.asyncio
async def test_busy_command_gives_up_with_a_readable_message():
    """When every attempt is busy the entity fails with the explanation."""
    session = _Session([*_task_id_calls(), *[(200, {"code": "A00082"})] * 3])
    api = _api(session)
    sleeps = []

    async def _sleep(delay):
        sleeps.append(delay)

    api._sleep = _sleep

    result = await api.send_command(
        vin="VIN",
        command_id="ve_1202",
        pin="1234",
        enabled=True,
        start_minutes=180,
        duration_hours=6,
    )

    assert result["ok"] is False
    assert result["code"] == "A00082"
    assert "zajęte" in result["message"]
    assert sleeps == list(COMMAND_BUSY_RETRY_DELAYS)
    assert session.request_count == 2 + len(COMMAND_BUSY_RETRY_DELAYS) + 1


@pytest.mark.asyncio
async def test_other_refusals_are_not_retried():
    """Only the busy code is worth a second attempt."""
    session = _Session([*_task_id_calls(), (200, {"code": "A00084"})])
    api = _api(session)
    sleeps = []

    async def _sleep(delay):
        sleeps.append(delay)

    api._sleep = _sleep

    result = await api.send_command(
        vin="VIN", command_id="ve_1209", pin="1234"
    )

    assert result["ok"] is False
    assert result["code"] == "A00084"
    assert sleeps == []
    assert session.request_count == 3
