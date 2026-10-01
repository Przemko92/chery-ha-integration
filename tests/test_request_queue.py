"""Queue and per-command spacing for Chery API requests."""

import asyncio

import pytest

from custom_components.chery_europe.api import CheryEuropeApi
from custom_components.chery_europe.const import COMMAND_MIN_INTERVAL_SECONDS
from custom_components.chery_europe.request_queue import (
    ApiRequestQueue,
    command_interval_key,
)


class _Clock:
    """Virtual clock whose sleep advances time without waiting."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


def test_command_interval_is_five_seconds():
    assert COMMAND_MIN_INTERVAL_SECONDS == 5


def test_command_interval_key_uses_vin_and_endpoint():
    assert (
        command_interval_key(
            "/asc/vehicleControl/airControl",
            {"vin": "VIN1"},
        )
        == "VIN1:airControl"
    )
    assert command_interval_key("asc/vehicleControl/lockControl", {"vin": "VIN1"}) == (
        "VIN1:lockControl"
    )


def test_command_interval_key_ignores_reads():
    assert command_interval_key("/asr/manager/realtime", {"vin": "VIN1"}) is None
    assert (
        command_interval_key(
            "/asc/vehicleControl/queryVehicleLocation",
            {"vin": "VIN1"},
        )
        is None
    )
    assert command_interval_key("/api/tsp/v1/app/vmc/queryList") is None


@pytest.mark.asyncio
async def test_same_command_is_not_sent_more_often_than_every_five_seconds():
    clock = _Clock()
    queue = ApiRequestQueue(clock=clock, sleep=clock.sleep)
    sent: list[tuple[str, float]] = []

    async def send(label: str) -> None:
        sent.append((label, clock.now))

    await queue.execute(lambda: send("a"), command_key="VIN:airControl")
    await queue.execute(lambda: send("b"), command_key="VIN:airControl")
    await queue.execute(lambda: send("lock"), command_key="VIN:lockControl")
    await queue.execute(lambda: send("other-vin"), command_key="VIN2:airControl")

    assert sent == [
        ("a", 0.0),
        ("b", 5.0),
        ("lock", 5.0),
        ("other-vin", 5.0),
    ]
    assert clock.sleeps == [5.0]


@pytest.mark.asyncio
async def test_partial_gap_waits_only_the_remainder():
    clock = _Clock()
    queue = ApiRequestQueue(min_interval=5, clock=clock, sleep=clock.sleep)

    async def send() -> None:
        return None

    await queue.execute(send, command_key="VIN:lockControl")
    clock.now = 2.0
    await queue.execute(send, command_key="VIN:lockControl")

    assert clock.sleeps == [3.0]
    assert clock.now == 5.0


@pytest.mark.asyncio
async def test_reads_are_serialized_without_the_command_interval():
    clock = _Clock()
    queue = ApiRequestQueue(clock=clock, sleep=clock.sleep)
    order: list[str] = []
    release = asyncio.Event()

    async def first() -> None:
        order.append("first-start")
        await release.wait()
        order.append("first-end")

    async def second() -> None:
        order.append("second-start")

    task1 = asyncio.create_task(queue.execute(first))
    await asyncio.sleep(0)
    task2 = asyncio.create_task(queue.execute(second))
    await asyncio.sleep(0)

    assert order == ["first-start"]
    release.set()
    await asyncio.gather(task1, task2)

    assert order == ["first-start", "first-end", "second-start"]
    assert clock.sleeps == []


@pytest.mark.asyncio
async def test_command_cooldown_does_not_block_other_requests():
    """The 5s wait holds the command gate, not the shared request slot."""
    clock = _Clock()
    in_cooldown = asyncio.Event()
    proceed = asyncio.Event()

    async def cooldown(delay: float) -> None:
        clock.sleeps.append(delay)
        in_cooldown.set()
        await proceed.wait()
        clock.now += delay

    queue = ApiRequestQueue(clock=clock, sleep=cooldown)

    async def send() -> str:
        return "sent"

    await queue.execute(send, command_key="VIN:airControl")
    waiting = asyncio.create_task(queue.execute(send, command_key="VIN:airControl"))
    await in_cooldown.wait()

    await asyncio.wait_for(queue.execute(send), timeout=1)

    proceed.set()
    assert await waiting == "sent"
    assert clock.sleeps == [5.0]


@pytest.mark.asyncio
async def test_nested_request_from_the_same_task_does_not_deadlock():
    """401 refresh retries re-enter the queue from inside the response handler."""
    queue = ApiRequestQueue(clock=lambda: 0.0, sleep=_Clock().sleep)
    seen: list[str] = []

    async def inner() -> str:
        seen.append("inner")
        return "ok"

    async def outer() -> str:
        seen.append("outer")
        return await queue.execute(inner)

    assert await queue.execute(outer) == "ok"
    assert seen == ["outer", "inner"]


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
        return str(self._payload)


class _Session:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        status, payload = self._responses.pop(0)
        return _Response(status, payload)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def _api(session) -> CheryEuropeApi:
    auth = type("Auth", (), {})()
    auth.access_token = "tok"
    auth.refresh_token_value = "ref"
    auth.needs_proactive_refresh = lambda quota=0.8: False
    api = CheryEuropeApi(auth, session)
    api._t_user_id = "user"
    api._user_token = "ut"
    return api


_TASK_OK = (200, {"code": "000000", "data": {"taskId": "TASK123"}})
_BFF_OK = (200, {"code": "000000"})
_CMD_OK = (200, {"code": "A00079"})


@pytest.mark.asyncio
async def test_api_spaces_repeated_vehicle_command():
    session = _Session([_BFF_OK, _TASK_OK, _CMD_OK, _CMD_OK])
    api = _api(session)
    clock = _Clock()
    api._request_queue._clock = clock
    api._request_queue._sleep = clock.sleep

    await api.send_command(vin="VIN", command_id="ve_1104", pin="1234", enabled=True)
    await api.send_command(vin="VIN", command_id="ve_1104", pin="1234", enabled=False)

    assert clock.sleeps == [5.0]
    assert session.calls[-1][1].endswith("/asc/vehicleControl/airControl")
    assert session.calls[-2][1].endswith("/asc/vehicleControl/airControl")


@pytest.mark.asyncio
async def test_api_does_not_space_different_commands():
    session = _Session([_BFF_OK, _TASK_OK, _CMD_OK, _CMD_OK])
    api = _api(session)
    clock = _Clock()
    api._request_queue._clock = clock
    api._request_queue._sleep = clock.sleep

    await api.send_command(vin="VIN", command_id="ve_1104", pin="1234", enabled=True)
    await api.send_command(vin="VIN", command_id="ve_1105", pin="1234", action="lock")

    assert clock.sleeps == []
