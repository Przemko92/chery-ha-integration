"""Persistent vehicle message history.

The message centre keeps hundreds of entries (563 on the reference account),
while the entity state can only expose a handful of them: Home Assistant drops
state attributes above 16 KiB.  The full history therefore lives in a
``Store`` file (survives restarts, no re-import on every boot) and is mirrored
to ``chery_messages.json`` in the configuration directory, keyed by VIN, so
older messages can be inspected or read from templates.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    MESSAGES_EXPORT_FILENAME,
    MESSAGES_HISTORY_LIMIT,
    MESSAGES_STORE_KEY,
    MESSAGES_STORE_VERSION,
)
from .messages import mark_all_read as flag_all_read
from .messages import merge_messages, sort_messages

_LOGGER = logging.getLogger(__name__)


class MessageHistory:
    """Whole inbox history of one config entry, cached in memory and on disk."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._vin: str | None = None
        self._store = Store(
            hass,
            MESSAGES_STORE_VERSION,
            MESSAGES_STORE_KEY.format(entry_id=entry_id),
        )
        self._messages: list[dict[str, Any]] = []
        self._backfilled_at: str | None = None
        self._loaded = False
        self._dirty = False

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Return the stored history, newest first."""
        return list(self._messages)

    @property
    def backfilled_at(self) -> str | None:
        """Return when the first, complete import ran (``None`` if never)."""
        return self._backfilled_at

    @property
    def is_empty(self) -> bool:
        """Return whether nothing has been stored yet."""
        return not self._messages

    def set_vin(self, vin: str | None) -> None:
        """Remember which car the history belongs to (export file key)."""
        if vin and vin != self._vin:
            self._vin = vin
            self._dirty = True

    async def async_load(self) -> list[dict[str, Any]]:
        """Read the stored history once; a broken file is treated as empty."""
        if self._loaded:
            return list(self._messages)
        self._loaded = True
        try:
            stored = await self._store.async_load()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Stored message history unreadable: %s", exc)
            stored = None
        if isinstance(stored, dict):
            raw = stored.get("messages")
            if isinstance(raw, list):
                self._messages = sort_messages(
                    item
                    for item in raw
                    if isinstance(item, dict) and item.get("id") is not None
                )
            backfilled = stored.get("backfilled_at")
            if isinstance(backfilled, str) and backfilled:
                self._backfilled_at = backfilled
            vin = stored.get("vin")
            if isinstance(vin, str) and vin:
                self._vin = vin
        return list(self._messages)

    def merge(self, incoming: list[dict[str, Any]]) -> int:
        """Merge freshly read messages into the history; return how many are new."""
        if not incoming:
            return 0
        self._messages, added = merge_messages(
            self._messages, incoming, limit=MESSAGES_HISTORY_LIMIT
        )
        self._dirty = True
        return added

    def mark_backfilled(self, stamp: str | None = None) -> None:
        """Record that the complete inbox has been imported once."""
        self._backfilled_at = stamp or datetime.now(UTC).isoformat()
        self._dirty = True

    def mark_all_read(self) -> int:
        """Flag every stored message as read; return how many changed."""
        self._messages, changed = flag_all_read(self._messages)
        if changed:
            self._dirty = True
        return changed

    async def async_save(self) -> None:
        """Persist the history and refresh the JSON export when it changed."""
        if not self._dirty:
            return
        self._dirty = False
        try:
            await self._store.async_save(
                {
                    "vin": self._vin,
                    "backfilled_at": self._backfilled_at,
                    "messages": self._messages,
                }
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("Storing the message history failed: %s", exc)
            self._dirty = True
        await self._async_export()

    async def _async_export(self) -> None:
        """Mirror the history into ``chery_messages.json`` for easy reading."""
        path = Path(self._hass.config.path(MESSAGES_EXPORT_FILENAME))
        key = self._vin or self._entry_id
        payload = await self._hass.async_add_executor_job(_read_export, path)
        payload[key] = {
            "updated": datetime.now(UTC).isoformat(),
            "backfilled_at": self._backfilled_at,
            "count": len(self._messages),
            "messages": self._messages,
        }
        try:
            await self._hass.async_add_executor_job(_write_export, path, payload)
        except OSError as exc:
            _LOGGER.debug("Writing %s failed: %s", path, exc)


def _read_export(path: Path) -> dict[str, Any]:
    """Return the current export file content, or an empty dict."""
    try:
        with path.open(encoding="utf-8") as handle:
            content = json.load(handle)
    except (OSError, ValueError):
        return {}
    return content if isinstance(content, dict) else {}


def _write_export(path: Path, payload: dict[str, Any]) -> None:
    """Write the export file atomically."""
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)
