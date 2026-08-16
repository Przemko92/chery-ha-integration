from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.chery_europe.const import CONF_ASK_FOR_PIN, CONF_PIN
from custom_components.chery_europe.pin import ask_for_pin, resolve_pin


def test_resolve_pin_prefers_service_call():
    entry = SimpleNamespace(options={CONF_PIN: "stored"})
    assert resolve_pin(entry, {"pin": "inline"}) == "inline"


def test_resolve_pin_uses_options_when_service_call_omits_pin():
    entry = SimpleNamespace(options={CONF_PIN: "stored"})
    assert resolve_pin(entry, {}) == "stored"


def test_resolve_pin_requires_configuration():
    entry = SimpleNamespace(options={})
    with pytest.raises(HomeAssistantError, match="Vehicle control PIN is not configured"):
        resolve_pin(entry, {})


def test_resolve_pin_ask_for_pin_requires_inline():
    entry = SimpleNamespace(options={CONF_PIN: "stored", CONF_ASK_FOR_PIN: True})
    with pytest.raises(HomeAssistantError, match="PIN is required"):
        resolve_pin(entry, {})


def test_resolve_pin_ask_for_pin_rejects_mismatch():
    entry = SimpleNamespace(options={CONF_PIN: "stored", CONF_ASK_FOR_PIN: True})
    with pytest.raises(HomeAssistantError, match="does not match"):
        resolve_pin(entry, {"pin": "wrong"})


def test_resolve_pin_ask_for_pin_accepts_matching_inline():
    entry = SimpleNamespace(options={CONF_PIN: "stored", CONF_ASK_FOR_PIN: True})
    assert resolve_pin(entry, {"pin": "stored"}) == "stored"


def test_ask_for_pin_defaults_false():
    assert ask_for_pin(SimpleNamespace(options={})) is False
    assert ask_for_pin(SimpleNamespace(options={CONF_ASK_FOR_PIN: True})) is True
