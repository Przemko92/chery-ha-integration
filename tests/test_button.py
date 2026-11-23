"""Tests for the Chery Europe button platform."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.components.button import ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from custom_components.chery_europe.button import (
    ACTION_BUTTONS,
    CheryEuropeActionButton,
)


def _action_button(action):
    """Build an action button without running the entity initialiser."""
    button = object.__new__(CheryEuropeActionButton)
    button.entity_description = ButtonEntityDescription(
        key="message_read",
        name="Message read",
        translation_key="message_read",
    )
    button._action = action
    return button


def _message_read_entry():
    for row in ACTION_BUTTONS:
        if row[0] == "message_read":
            return row
    raise AssertionError("message_read missing from ACTION_BUTTONS")


def test_message_read_button_is_a_configuration_action():
    """The read button sits in configuration and calls the read coordinator method."""
    key, name, translation_key, icon, category, action_attr = _message_read_entry()

    assert key == "message_read"
    assert name == "Message read"
    assert translation_key == "message_read"
    assert icon == "mdi:email-open-outline"
    assert category is EntityCategory.CONFIG
    assert action_attr == "async_mark_messages_read"


def test_press_runs_the_action_once():
    """Pressing the button runs the bound coordinator action once."""
    calls: list[int] = []

    async def action():
        calls.append(1)
        return True

    asyncio.run(_action_button(action).async_press())

    assert calls == [1]


def test_press_raises_when_the_cloud_refuses():
    """A refused call surfaces as HomeAssistantError instead of failing silently."""

    async def action():
        return False

    with pytest.raises(HomeAssistantError):
        asyncio.run(_action_button(action).async_press())


def test_press_swallows_action_exceptions():
    """An exception in the action is logged, not raised at the user."""

    async def action():
        raise RuntimeError("boom")

    assert asyncio.run(_action_button(action).async_press()) is None
