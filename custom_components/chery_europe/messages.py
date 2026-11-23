"""Vehicle messages (message centre) helpers.

The Chery app keeps a per-account inbox of vehicle messages (low SOC, tyre
temperature, scheduled-trip confirmations, service notices...).  They are read
from ``/api/message/v1/message/inbox/inboxs/C/pagingToC`` with a POST body of
``{"pageNo": n, "pageSize": n}``.  The payload carries ``title``, ``content``
(already localised by the server) and ``sendTime`` as epoch milliseconds, so
this module only normalises and renders it -- no translation tables needed.

Messages are stored as plain dicts so they survive in ``CheryData`` and in the
entity attributes unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from .const import (
    MESSAGES_ATTRIBUTE_ITEMS,
    MESSAGES_HISTORY_CHARS,
    MESSAGES_HISTORY_ITEMS,
)

# ``status`` is 0 for an unread message and 1 once the app has opened it.
STATUS_UNREAD = 0

MESSAGE_DATE_FORMAT = "%Y-%m-%d %H:%M"


def _unwrap(payload: Any) -> dict[str, Any]:
    """Return the ``data`` envelope of a BFF response when it is nested."""
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    if isinstance(data, dict) and "records" in data:
        return data
    return payload


def _as_bool(value: Any) -> bool | None:
    """Coerce a BFF boolean-ish value (``True``/``"1"``/1) to a bool."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    return None


def _received(stamp: Any) -> str | None:
    """Convert ``sendTime`` (epoch ms, as string) to an ISO timestamp."""
    if stamp is None:
        return None
    try:
        value = float(stamp)
    except (TypeError, ValueError):
        return None
    # The app sends milliseconds; tolerate seconds just in case.
    if value > 1e11:
        value /= 1000
    try:
        return datetime.fromtimestamp(value, tz=UTC).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def parse_messages(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
    """Parse one page of the inbox.

    Returns the messages of the page (newest first, as the server sends them)
    and the ``total`` entry count reported by the server (``None`` when the
    payload carries no paging metadata).
    """
    page = _unwrap(payload)
    records = page.get("records")
    if not isinstance(records, list):
        return [], None
    total = page.get("total")
    try:
        total_count = int(total) if total is not None else None
    except (TypeError, ValueError):
        total_count = None
    messages: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or record.get("id") is None:
            continue
        status = record.get("status")
        read = True
        if isinstance(status, (int, str)):
            try:
                read = int(status) != STATUS_UNREAD
            except (TypeError, ValueError):
                read = True
        messages.append(
            {
                "id": str(record["id"]),
                "title": str(record.get("title") or ""),
                "text": str(record.get("content") or ""),
                "received": _received(record.get("sendTime")),
                "read": read,
                "type": record.get("messageTypeCode"),
                "level": record.get("level"),
            }
        )
    return messages, total_count


def parse_unread_messages(payload: Any) -> bool | None:
    """Parse ``getUnread``, which answers with a bare flag inside ``data``."""
    if not isinstance(payload, dict):
        return None
    if payload.get("code") not in (0, "0", None):
        return None
    return _as_bool(payload.get("data"))


def message_line(message: dict[str, Any]) -> str:
    """Render ``date -- title: text`` for one message on a single line."""
    parts: list[str] = []
    received = message.get("received")
    if isinstance(received, str) and received:
        try:
            parts.append(
                datetime.fromisoformat(received).strftime(MESSAGE_DATE_FORMAT)
            )
        except ValueError:
            parts.append(received)
    title = str(message.get("title") or "").strip()
    text = " ".join(str(message.get("text") or "").split())
    if title and text and title not in text:
        parts.append(f"{title}: {text}")
    elif title or text:
        parts.append(text or title)
    return " — ".join(parts)


def messages_content(messages: Iterable[dict[str, Any]]) -> str:
    """Render the fetched messages as one line each."""
    return "\n".join(line for line in (message_line(m) for m in messages) if line)


def messages_history(
    messages: Iterable[dict[str, Any]],
    limit: int = MESSAGES_HISTORY_ITEMS,
    char_budget: int = MESSAGES_HISTORY_CHARS,
) -> list[str]:
    """Render the newest messages as one line each, newest first, within a size budget.

    The attribute payload has to fit the recorder's 16 KiB per state, so the list stops
    at ``limit`` entries or ``char_budget`` characters, whichever comes first.
    """
    lines: list[str] = []
    used = 0
    for message in messages:
        line = message_line(message)
        if not line:
            continue
        if len(lines) >= limit or used + len(line) > char_budget:
            break
        lines.append(line)
        used += len(line)
    return lines


def unread_count(messages: Iterable[dict[str, Any]]) -> int:
    """Count the unread messages inside the given list."""
    return sum(1 for message in messages if not message.get("read", True))


def unread_messages(messages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only the unread messages, newest first."""
    return [m for m in messages if not m.get("read", True)]


def sort_messages(messages: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort messages newest first; entries without a timestamp go last."""
    return sorted(
        messages,
        key=lambda message: str(message.get("received") or ""),
        reverse=True,
    )


def merge_messages(
    existing: Iterable[dict[str, Any]],
    incoming: Iterable[dict[str, Any]],
    *,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Merge freshly read messages into the stored history, keyed by ``id``.

    Fresh records win (the read flag may have changed in the app), the result
    is newest first and optionally capped at ``limit`` entries.  Returns the
    merged list and how many ids were new.
    """
    merged: dict[str, dict[str, Any]] = {}
    for message in existing:
        message_id = message.get("id")
        if message_id is not None:
            merged[str(message_id)] = message
    known = set(merged)
    added = 0
    for message in incoming:
        message_id = message.get("id")
        if message_id is None:
            continue
        key = str(message_id)
        if key not in known:
            known.add(key)
            added += 1
        merged[key] = message
    items = sort_messages(merged.values())
    if limit is not None and len(items) > limit:
        items = items[:limit]
    return items, added


def messages_attributes(
    messages: Iterable[dict[str, Any]],
    *,
    total: int | None,
    unread: bool | None,
    polled_at: str | None,
    unread_total: int | None = None,
    backfilled_at: str | None = None,
    limit: int = MESSAGES_ATTRIBUTE_ITEMS,
) -> dict[str, Any]:
    """Build the extra state attributes of the messages sensor.

    The stored history can be thousands of entries and Home Assistant drops
    state attributes above 16 KiB, so only the newest ``limit`` messages are
    exposed here.  The complete history lives in the store and in the export
    file (see ``message_history``).
    """
    items = sort_messages(messages)
    unread_items = unread_messages(items)
    return {
        "last_updated": polled_at,
        "total": total,
        "unread": unread,
        "unread_count": unread_total if unread_total is not None else len(unread_items),
        "count": len(items),
        "oldest": items[-1]["received"] if items else None,
        "newest": items[0]["received"] if items else None,
        "latest": items[0] if items else None,
        "last_message": items[0] if items else None,
        "last_message_text": items[0]["text"] if items else None,
        "backfilled_at": backfilled_at,
        "messages_truncated": len(items) > limit,
        "messages": items[:limit],
    }


def last_message_attributes(message: dict[str, Any] | None) -> dict[str, Any]:
    """Build the attributes of the "last message" sensor."""
    if not message:
        return {
            "received": None,
            "text": None,
            "read": None,
            "id": None,
            "type": None,
            "level": None,
        }
    return {
        "received": message.get("received"),
        "text": message.get("text"),
        "read": message.get("read"),
        "id": message.get("id"),
        "type": message.get("type"),
        "level": message.get("level"),
    }
