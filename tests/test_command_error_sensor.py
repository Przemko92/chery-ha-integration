"""Diagnostics entities carry the last refused command code and its text.

The car answers a refusal with a bare code (``A00082``), so the reason has to
land somewhere readable: the coordinator mirrors every command outcome into
``command_error_code`` / ``command_error_text`` and two diagnostic sensors
publish them.
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.api import CheryEuropeApi
from custom_components.chery_europe.const import NO_COMMAND_ERROR
from custom_components.chery_europe.coordinator import CheryEuropeDataUpdateCoordinator
from custom_components.chery_europe.data import CheryData
from custom_components.chery_europe.request_queue import ApiRequestQueue
from custom_components.chery_europe.sensor import STATUS_SENSOR_DESCRIPTIONS

VIN = "VIN123"
BUSY_TEXT = "auto zajęte — wykonuje inną komendę, ponów za kilka sekund"


class _Response:
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
    def __init__(self, responses):
        self._responses = list(responses)
        self.request_count = 0

    def _next(self):
        status, payload = (
            self._responses[self.request_count]
            if self.request_count < len(self._responses)
            else (200, {})
        )
        self.request_count += 1
        return _Response(status, payload)

    def request(self, method, url, **kwargs):
        return self._next()

    def post(self, url, **kwargs):
        return self._next()


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
    api._request_queue = ApiRequestQueue(min_interval=0)

    async def _sleep(_delay):
        return None

    api._sleep = _sleep
    return api


def _coordinator(api=None, *, vin=None):
    hass = Mock()
    hass.config_entries = Mock(async_update_entry=Mock())
    hass.async_create_task = Mock()
    entry = SimpleNamespace(options={}, title="Chery Europe")
    with patch(
        "custom_components.chery_europe.coordinator.DataUpdateCoordinator.__init__",
        return_value=None,
    ):
        coordinator = CheryEuropeDataUpdateCoordinator(
            hass, api or SimpleNamespace(), entry, None, vin=vin
        )
    coordinator.hass = hass
    coordinator.async_set_updated_data = Mock(
        side_effect=lambda data: setattr(coordinator, "data", data) or data
    )
    coordinator.data = CheryData(vin=vin or VIN)
    return coordinator


def _task_id_calls():
    return [
        (200, {"code": "000000"}),
        (200, {"code": "000000", "data": {"taskId": "T1"}}),
    ]


def _sensor(coordinator, key):
    description = next(d for d in STATUS_SENSOR_DESCRIPTIONS if d.key == key)
    return description.value_fn(coordinator.data)


@pytest.mark.asyncio
async def test_api_reports_both_accepted_and_refused_commands():
    """Every vehicle command outcome reaches the registered callbacks."""
    # The taskId is cached after the first command, so the second one costs a
    # single request.
    session = _Session(
        [*_task_id_calls(), (200, {"code": "A00079"}), (200, {"code": "A00084"})]
    )
    api = _api(session)
    seen = []
    api.command_result_callbacks.append(
        lambda vin, command_id, result: seen.append((vin, command_id, result["ok"]))
    )

    await api.send_command(vin=VIN, command_id="ve_1202", pin="1234", enabled=True)
    await api.send_command(vin=VIN, command_id="ve_1202", pin="1234", enabled=True)

    assert seen == [(VIN, "ve_1202", True), (VIN, "ve_1202", False)]


@pytest.mark.asyncio
async def test_a_broken_callback_does_not_break_the_command():
    """Diagnostics are best effort: they never turn a command into a failure."""
    session = _Session([*_task_id_calls(), (200, {"code": "A00079"})])
    api = _api(session)
    api.command_result_callbacks.append(lambda *args: 1 / 0)

    result = await api.send_command(
        vin=VIN, command_id="ve_1202", pin="1234", enabled=True
    )

    assert result["ok"] is True


def test_refused_command_fills_the_error_entities():
    """The code and the readable text both land in the sensor data."""
    coordinator = _coordinator()

    coordinator._handle_command_result(
        VIN, "ve_1202", {"ok": False, "code": "A00082", "message": BUSY_TEXT}
    )

    assert _sensor(coordinator, "command_error_code") == "A00082"
    assert _sensor(coordinator, "command_error_text") == BUSY_TEXT


def test_accepted_command_clears_the_error():
    """A command that goes through must not leave a stale failure behind."""
    coordinator = _coordinator()
    coordinator._handle_command_result(
        VIN, "ve_1202", {"ok": False, "code": "A00082", "message": BUSY_TEXT}
    )

    coordinator._handle_command_result(VIN, "ve_1202", {"ok": True, "code": "A00079"})

    assert _sensor(coordinator, "command_error_code") == NO_COMMAND_ERROR
    assert _sensor(coordinator, "command_error_text") == NO_COMMAND_ERROR


def test_background_locate_keeps_the_last_refusal_visible():
    """ve_1209 only asks the car to answer, so it says nothing about control."""
    coordinator = _coordinator()
    coordinator._handle_command_result(
        VIN, "ve_1202", {"ok": False, "code": "A00082", "message": BUSY_TEXT}
    )

    coordinator._handle_command_result(VIN, "ve_1209", {"ok": True, "code": "A00079"})

    assert _sensor(coordinator, "command_error_code") == "A00082"


def test_another_vehicle_is_ignored():
    """A second car in the same account keeps its own error entities."""
    coordinator = _coordinator(vin=VIN)

    coordinator._handle_command_result(
        "OTHER-VIN", "ve_1202", {"ok": False, "code": "A00082", "message": BUSY_TEXT}
    )

    assert coordinator.data.command_error_code is None


def test_error_sensors_start_with_no_error():
    """Nothing sent yet reads as "brak", never as an unknown value."""
    coordinator = _coordinator()

    assert _sensor(coordinator, "command_error_code") == NO_COMMAND_ERROR
    assert _sensor(coordinator, "command_error_text") == NO_COMMAND_ERROR


@pytest.mark.asyncio
async def test_failed_command_reaches_the_entities_end_to_end():
    """A real send_command refusal is published without any entity code."""
    session = _Session([*_task_id_calls(), *[(200, {"code": "A00082"})] * 3])
    api = _api(session)
    coordinator = _coordinator(api)

    result = await api.send_command(
        vin=VIN, command_id="ve_1202", pin="1234", enabled=True
    )

    assert result["ok"] is False
    assert _sensor(coordinator, "command_error_code") == "A00082"
    assert "zajęte" in _sensor(coordinator, "command_error_text")
