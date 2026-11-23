"""Tests for the vehicle message inbox helpers."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.chery_europe.data import CheryData, apply_messages
from custom_components.chery_europe.messages import (
    message_line,
    messages_attributes,
    messages_content,
    parse_messages,
    parse_unread_messages,
    unread_count,
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


def test_messages_attributes_count_the_page():
    """The attributes carry the total, the unread flag and the messages."""
    messages, total = parse_messages(PAGE)

    attributes = messages_attributes(
        messages,
        total=total,
        unread=True,
        polled_at="2026-11-23T10:30:00+00:00",
    )

    assert attributes["total"] == 563
    assert attributes["count"] == 2
    assert attributes["unread"] is True
    assert attributes["unread_in_page"] == 1
    assert attributes["latest"]["id"] == "1001"
    assert attributes["last_updated"] == "2026-11-23T10:30:00+00:00"


def test_apply_messages_keeps_the_last_page_on_failure():
    """None (a failed read) must not wipe what the inbox already showed."""
    messages, total = parse_messages(PAGE)
    data = CheryData(vin="VIN")

    filled = apply_messages(
        data, messages, total=total, unread=True, polled_at="2026-11-23T10:30:00+00:00"
    )
    assert filled.messages_total == 563
    assert filled.messages_unread is True

    kept = apply_messages(filled, None)
    assert kept.messages == messages
    assert kept.messages_unread is True


def test_merge_messages_is_throttled():
    """A second update inside the interval sends no inbox request at all."""
    from custom_components.chery_europe.coordinator import (
        CheryEuropeDataUpdateCoordinator,
    )

    calls: list[int] = []

    async def fetch_messages(page=1, page_size=10):
        calls.append(1)
        return PAGE

    async def fetch_messages_unread():
        return True

    coordinator = object.__new__(CheryEuropeDataUpdateCoordinator)
    coordinator.api = SimpleNamespace(
        fetch_messages=fetch_messages, fetch_messages_unread=fetch_messages_unread
    )
    coordinator._messages_polled_at = datetime.now(UTC)

    result = asyncio.run(coordinator._merge_messages(CheryData(vin="VIN")))

    assert calls == []
    assert result.messages is None

    coordinator._messages_polled_at = datetime.now(UTC) - timedelta(minutes=31)
    result = asyncio.run(coordinator._merge_messages(CheryData(vin="VIN")))

    assert calls == [1]
    assert result.messages_total == 563
    assert result.messages_unread is True


def test_message_sensors_expose_count_and_texts():
    """The message sensors report the inbox total, the flag and the texts."""
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
        polled_at="2026-11-23T10:30:00+00:00",
    )
    coordinator = SimpleNamespace(data=data, last_update_success=True)
    sensors = {}
    for description in MESSAGE_SENSOR_DESCRIPTIONS:
        sensor = object.__new__(CheryEuropeMessageSensor)
        sensor.entity_description = description
        sensor.coordinator = coordinator
        sensors[description.key] = sensor

    assert sensors["messages"].native_value == 563
    assert sensors["messages_content"].native_value.startswith("2026-11-")
    assert "Tyre temperature warning" in sensors["messages_content"].native_value
    attributes = sensors["messages"].extra_state_attributes
    assert attributes["unread"] is True
    assert attributes["total"] == 563
    assert attributes["messages"][0]["id"] == "1001"
