"""Tests for the vehicle message inbox helpers."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.chery_europe.data import CheryData, apply_messages
from custom_components.chery_europe.messages import (
    last_message_attributes,
    merge_messages,
    message_line,
    messages_attributes,
    messages_content,
    parse_messages,
    parse_unread_messages,
    unread_count,
    unread_messages,
)

PAGE = {
    "code": 0,
    "msg": "操作成功",
    "data": {
        "records": [
            {
                "id": 1001,
                "title": "Tyre temperature warning",
                "content": "The temperature of the right front tyre is abnormal.",
                "sendTime": 1795080001988,
                "status": 0,
                "messageTypeCode": "vehicleMessage",
                "level": "WARNING",
            },
            {
                "id": 1000,
                "title": "Scheduled departure",
                "content": "Charging will start at 06:40 before the departure.",
                "sendTime": 1700000000000,
                "status": 1,
                "messageTypeCode": "vehicleMessage",
                "level": "NORMAL",
            },
        ],
        "total": 563,
        "pageNo": 1,
        "pageSize": 10,
    },
}


def test_parse_messages_reads_records_and_total():
    """A page yields plain dicts, the unread flag and the inbox total."""
    messages, total = parse_messages(PAGE)

    assert total == 563
    assert [m["id"] for m in messages] == ["1001", "1000"]
    assert messages[0]["read"] is False
    assert messages[1]["read"] is True
    assert messages[0]["title"] == "Tyre temperature warning"
    assert messages[0]["type"] == "vehicleMessage"
    assert datetime.fromisoformat(messages[1]["received"]) == datetime(
        2023, 11, 14, 22, 13, 20, tzinfo=UTC
    )


def test_parse_messages_tolerates_broken_payloads():
    """A missing or malformed page is an empty page, never an exception."""
    assert parse_messages(None) == ([], None)
    assert parse_messages({}) == ([], None)
    assert parse_messages({"data": {"records": "nope"}}) == ([], None)
    messages, total = parse_messages({"data": {"records": [{"content": "x"}]}})
    assert messages == []
    assert total is None


def test_parse_unread_messages_reads_the_flag():
    """getUnread answers with a bare boolean under data."""
    assert parse_unread_messages({"code": 0, "data": True}) is True
    assert parse_unread_messages({"code": 0, "data": False}) is False
    assert parse_unread_messages({"code": 0, "data": "1"}) is True
    assert parse_unread_messages({"code": 1, "data": True}) is None
    assert parse_unread_messages(None) is None


def test_message_line_and_content_render_date_title_text():
    """Each message becomes one line: date — title: text."""
    messages, _ = parse_messages(PAGE)

    line = message_line(messages[1])
    assert line == (
        "2023-11-14 22:13 — Scheduled departure: Charging will start at 06:40 "
        "before the departure."
    )
    assert messages_content(messages).count("\n") == 1
    assert unread_count(messages) == 1


def test_merge_messages_dedupes_by_id_and_keeps_the_newest_first():
    """A fresh record wins over the stored one and the history stays sorted."""
    stored, _ = parse_messages(PAGE)
    stored[0]["read"] = True  # the phone app read it later

    incoming = [
        {
            "id": "1001",
            "title": "Tyre temperature warning",
            "text": "still there",
            "received": "2026-11-19T09:20:01.988000+00:00",
            "read": False,
            "type": "vehicleMessage",
            "level": "NORMAL",
        },
        {
            "id": "1002",
            "title": "Service due",
            "text": "Book a service",
            "received": "2026-11-20T08:00:00+00:00",
            "read": False,
            "type": "vehicleMessage",
            "level": "NORMAL",
        },
    ]

    merged, added = merge_messages(stored, incoming)

    assert added == 1
    assert [m["id"] for m in merged] == ["1002", "1001", "1000"]
    assert merged[1]["read"] is False
    assert len(merge_messages(merged, incoming, limit=2)[0]) == 2


def test_unread_helpers_count_the_whole_history():
    """Unread counting and listing work over the stored history."""
    messages, _ = parse_messages(PAGE)
    assert unread_count(messages) == 1
    assert [m["id"] for m in unread_messages(messages)] == ["1001"]


def test_messages_attributes_count_the_history_and_cap_the_list():
    """The attributes summarise the history and expose only the newest page."""
    messages, total = parse_messages(PAGE)
    history = messages * 12  # over the attribute limit

    attributes = messages_attributes(
        history,
        total=total,
        unread=True,
        polled_at="2026-11-23T10:30:00+00:00",
        unread_total=5,
        backfilled_at="2026-11-23T10:00:00+00:00",
    )

    assert attributes["total"] == 563
    assert attributes["count"] == 24
    assert attributes["unread"] is True
    assert attributes["unread_count"] == 5
    assert attributes["latest"]["id"] == "1001"
    assert attributes["newest"] > attributes["oldest"]
    assert attributes["backfilled_at"] == "2026-11-23T10:00:00+00:00"
    assert attributes["messages_truncated"] is True
    assert len(attributes["messages"]) == 20
    assert attributes["last_updated"] == "2026-11-23T10:30:00+00:00"


def test_last_message_attributes_describe_the_newest_entry():
    """The last-message sensor exposes title, date, text and read flag."""
    messages, _ = parse_messages(PAGE)

    attributes = last_message_attributes(messages[0])

    assert attributes["received"] == "2026-11-19T09:20:01.988000+00:00"
    assert attributes["text"].startswith("The temperature")
    assert attributes["read"] is False
    assert attributes["id"] == "1001"
    assert last_message_attributes(None)["id"] is None


def test_apply_messages_keeps_the_last_page_on_failure():
    """None (a failed read) must not wipe what the inbox already showed."""
    messages, total = parse_messages(PAGE)
    data = CheryData(vin="VIN")

    filled = apply_messages(
        data,
        messages,
        total=total,
        unread=True,
        unread_count=1,
        polled_at="2026-11-23T10:30:00+00:00",
        backfilled_at="2026-11-23T10:00:00+00:00",
    )
    assert filled.messages_total == 563
    assert filled.messages_unread is True
    assert filled.messages_unread_count == 1
    assert filled.messages_backfilled_at == "2026-11-23T10:00:00+00:00"

    kept = apply_messages(filled, None)
    assert kept.messages == messages
    assert kept.messages_unread is True


class FakeHistory:
    """Stand-in for ``MessageHistory`` without Home Assistant imports."""

    def __init__(self, messages=None):
        self._messages = list(messages or [])
        self._backfilled_at = "2026-11-23T10:00:00+00:00" if messages else None
        self.saved = 0

    @property
    def messages(self):
        return list(self._messages)

    @property
    def is_empty(self):
        return not self._messages

    @property
    def backfilled_at(self):
        return self._backfilled_at

    def set_vin(self, vin):
        self.vin = vin

    async def async_load(self):
        return list(self._messages)

    def merge(self, incoming):
        self._messages, added = merge_messages(self._messages, incoming)
        return added

    def mark_backfilled(self, stamp=None):
        self._backfilled_at = stamp or "now"

    async def async_save(self):
        self.saved += 1


def _coordinator(fetch, unread=None, history=None, polled_at=None):
    from custom_components.chery_europe.coordinator import (
        CheryEuropeDataUpdateCoordinator,
    )

    coordinator = object.__new__(CheryEuropeDataUpdateCoordinator)
    api = SimpleNamespace(fetch_messages=fetch)
    if unread is not None:
        api.fetch_messages_unread = unread
    coordinator.api = api
    coordinator._messages_polled_at = polled_at
    coordinator._messages_rescanned_at = None
    coordinator._message_history = history or FakeHistory()
    return coordinator


def test_merge_messages_is_throttled():
    """A second update inside the interval sends no inbox request at all."""
    calls: list[tuple[int, int]] = []

    async def fetch_messages(page=1, page_size=10):
        calls.append((page, page_size))
        return PAGE

    async def fetch_messages_unread():
        return True

    coordinator = _coordinator(
        fetch_messages, fetch_messages_unread, polled_at=datetime.now(UTC)
    )

    result = asyncio.run(coordinator._merge_messages(CheryData(vin="VIN")))

    assert calls == []
    assert result.messages is None

    coordinator._messages_polled_at = datetime.now(UTC) - timedelta(minutes=31)
    result = asyncio.run(coordinator._merge_messages(CheryData(vin="VIN")))

    assert calls == [(1, 200)]  # first run imports the whole inbox
    assert result.messages_total == 563
    assert result.messages_unread is True
    assert result.messages_unread_count == 1
    assert result.messages_backfilled_at is not None


def test_merge_messages_reuses_the_stored_history():
    """With a stored history only the newest page is read and merged."""
    calls: list[tuple[int, int]] = []
    stored, _ = parse_messages(PAGE)

    async def fetch_messages(page=1, page_size=10):
        calls.append((page, page_size))
        return {
            "code": 0,
            "data": {
                "records": [
                    {
                        "id": 1002,
                        "title": "Service due",
                        "content": "Book a service",
                        "sendTime": 1795300000000,
                        "status": 0,
                    }
                ],
                "total": 564,
            },
        }

    async def fetch_messages_unread():
        return True

    coordinator = _coordinator(
        fetch_messages, fetch_messages_unread, history=FakeHistory(stored)
    )

    result = asyncio.run(coordinator._merge_messages(CheryData(vin="VIN")))

    assert calls == [(1, 50)]
    messages = result.messages
    assert messages is not None
    assert len(messages) == 3
    assert messages[0]["id"] == "1002"
    assert result.messages_total == 564
    assert result.messages_unread_count == 2


def test_merge_messages_rescans_when_the_unread_flag_disagrees():
    """A read in the phone app flips the cloud flag; one rescan follows."""
    calls: list[tuple[int, int]] = []
    stored, _ = parse_messages(PAGE)  # one unread entry

    read_1001 = {
        "id": 1001,
        "title": "Tyre temperature warning",
        "content": "read already",
        "sendTime": 1795080001988,
        "status": 1,
    }

    async def fetch_messages(page=1, page_size=10):
        calls.append((page, page_size))
        records = [read_1001] if page_size == 200 else []
        return {"code": 0, "data": {"records": records, "total": 563}}

    async def fetch_messages_unread():
        return False

    coordinator = _coordinator(
        fetch_messages, fetch_messages_unread, history=FakeHistory(stored)
    )

    result = asyncio.run(coordinator._merge_messages(CheryData(vin="VIN")))

    assert calls[0] == (1, 50)
    assert calls[1] == (1, 200)
    assert result.messages_unread_count == 0
    assert coordinator._messages_rescanned_at is not None


def test_message_sensors_expose_count_unread_and_last_message():
    """The message sensors report the history size, unread count and last entry."""
    pytest.importorskip("homeassistant")
    from custom_components.chery_europe.sensor import (
        MESSAGE_SENSOR_DESCRIPTIONS,
        CheryEuropeMessageSensor,
    )

    messages, total = parse_messages(PAGE)
    data = apply_messages(
        CheryData(vin="VIN"),
        messages,
        total=total,
        unread=True,
        unread_count=1,
        polled_at="2026-11-23T10:30:00+00:00",
        backfilled_at="2026-11-23T10:00:00+00:00",
    )
    coordinator = SimpleNamespace(data=data, last_update_success=True)
    sensors = {}
    for description in MESSAGE_SENSOR_DESCRIPTIONS:
        sensor = object.__new__(CheryEuropeMessageSensor)
        sensor.entity_description = description
        sensor.coordinator = coordinator
        sensors[description.key] = sensor

    assert sensors["messages"].native_value == 563
    assert sensors["messages_unread"].native_value == 1
    assert sensors["last_message"].native_value == "Tyre temperature warning"
    assert sensors["messages_content"].native_value.startswith("2026-11-")
    assert "Tyre temperature warning" in sensors["messages_content"].native_value

    attributes = sensors["messages"].extra_state_attributes
    assert attributes["total"] == 563
    assert attributes["unread_count"] == 1
    assert attributes["latest"]["id"] == "1001"
    assert attributes["backfilled_at"] == "2026-11-23T10:00:00+00:00"
    assert "messages" not in attributes or len(attributes["messages"]) == 2

    unread = sensors["messages_unread"].extra_state_attributes
    assert unread["unread_count"] == 1
    assert unread["unread"][0].startswith("2026-11-19")
    assert sensors["last_message"].extra_state_attributes["read"] is False
    assert sensors["messages_content"].extra_state_attributes == {}


def test_messages_page_slices_the_stored_history():
    """The get_messages service pages through the local copy only."""
    stored, _ = parse_messages(PAGE)

    async def fetch_messages(page=1, page_size=10):
        raise AssertionError("the service must not touch the cloud")

    coordinator = _coordinator(fetch_messages, history=FakeHistory(stored))

    first = asyncio.run(coordinator.async_messages_page(1, 1))
    assert first["total"] == 2
    assert first["pages"] == 2
    assert [m["id"] for m in first["messages"]] == ["1001"]
    assert first["backfilled_at"] == "2026-11-23T10:00:00+00:00"

    second = asyncio.run(coordinator.async_messages_page(9, 1))
    assert second["page"] == 2
    assert [m["id"] for m in second["messages"]] == ["1000"]

    unread = asyncio.run(coordinator.async_messages_page(1, 10, unread_only=True))
    assert unread["total"] == 1
    assert [m["id"] for m in unread["messages"]] == ["1001"]
