from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.chery_europe.const import CONF_PIN
from custom_components.chery_europe.pin import resolve_pin


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
