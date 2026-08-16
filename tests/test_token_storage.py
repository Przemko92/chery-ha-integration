# pyright: reportAttributeAccessIssue=false, reportMissingImports=false
from unittest.mock import Mock

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_SECRET,
    CONF_EXPIRES_IN,
    CONF_LOGIN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_OBTAINED_AT,
)
from custom_components.chery_europe.token_storage import (
    clear_tokens,
    read_client_secret,
    read_token_expiry,
    read_tokens,
    token_data_from_response,
    write_tokens,
)
from custom_components.chery_europe.types.auth_models import AuthResponse


def _entry(data):
    entry = Mock()
    entry.data = dict(data)
    return entry


def _hass():
    hass = Mock()

    def async_update_entry(entry, data):
        entry.data = dict(data)

    hass.config_entries.async_update_entry = async_update_entry
    return hass


def _response(access_token="acc", refresh_token="ref", expires_in=3600):
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
        token_type="Bearer",
    )


# ── read_tokens ───────────────────────────────────────────────────────────────


def test_read_tokens_returns_access_and_refresh():
    entry = _entry({CONF_ACCESS_TOKEN: "a", CONF_REFRESH_TOKEN: "r"})
    assert read_tokens(entry) == ("a", "r")


def test_read_tokens_missing_returns_none():
    entry = _entry({})
    assert read_tokens(entry) == (None, None)


def test_read_client_secret_returns_value():
    entry = _entry({CONF_CLIENT_SECRET: "secret"})
    assert read_client_secret(entry) == "secret"


def test_read_client_secret_missing_returns_none():
    entry = _entry({})
    assert read_client_secret(entry) is None


def test_read_token_expiry_returns_values():
    entry = _entry({CONF_EXPIRES_IN: 43200, CONF_TOKEN_OBTAINED_AT: 1700000000.5})
    assert read_token_expiry(entry) == (43200, 1700000000.5)


def test_read_token_expiry_missing_returns_defaults():
    entry = _entry({})
    assert read_token_expiry(entry) == (0, None)


# ── token_data_from_response ──────────────────────────────────────────────────


def test_token_data_from_response_without_client_secret():
    data = token_data_from_response(_response("a", "r"), obtained_at=1234.0)
    assert data == {
        CONF_ACCESS_TOKEN: "a",
        CONF_REFRESH_TOKEN: "r",
        CONF_EXPIRES_IN: 3600,
        CONF_TOKEN_OBTAINED_AT: 1234.0,
    }
    assert CONF_CLIENT_SECRET not in data


def test_token_data_from_response_with_client_secret():
    data = token_data_from_response(
        _response("a", "r"), client_secret="cs", obtained_at=99.0
    )
    assert data == {
        CONF_ACCESS_TOKEN: "a",
        CONF_REFRESH_TOKEN: "r",
        CONF_EXPIRES_IN: 3600,
        CONF_TOKEN_OBTAINED_AT: 99.0,
        CONF_CLIENT_SECRET: "cs",
    }


def test_token_data_from_response_sets_obtained_at_when_omitted():
    before = __import__("time").time()
    data = token_data_from_response(_response("a", "r"))
    after = __import__("time").time()
    assert before <= data[CONF_TOKEN_OBTAINED_AT] <= after


# ── write_tokens ──────────────────────────────────────────────────────────────


def test_write_tokens_persists_access_and_refresh():
    hass = _hass()
    entry = _entry({CONF_LOGIN: "user"})
    write_tokens(hass, entry, _response("new_a", "new_r"), obtained_at=42.0)
    assert entry.data[CONF_ACCESS_TOKEN] == "new_a"
    assert entry.data[CONF_REFRESH_TOKEN] == "new_r"
    assert entry.data[CONF_EXPIRES_IN] == 3600
    assert entry.data[CONF_TOKEN_OBTAINED_AT] == 42.0
    assert entry.data[CONF_LOGIN] == "user"
    assert CONF_CLIENT_SECRET not in entry.data


def test_write_tokens_persists_client_secret():
    hass = _hass()
    entry = _entry({CONF_LOGIN: "user"})
    write_tokens(hass, entry, _response("a", "r"), client_secret="cs", obtained_at=1.0)
    assert entry.data[CONF_CLIENT_SECRET] == "cs"
    assert entry.data[CONF_ACCESS_TOKEN] == "a"
    assert entry.data[CONF_REFRESH_TOKEN] == "r"


def test_write_tokens_without_client_secret_preserves_existing():
    hass = _hass()
    entry = _entry({CONF_LOGIN: "user", CONF_CLIENT_SECRET: "old_cs"})
    write_tokens(hass, entry, _response("a", "r"), obtained_at=1.0)
    assert entry.data[CONF_CLIENT_SECRET] == "old_cs"


# ── clear_tokens ──────────────────────────────────────────────────────────────


def test_clear_tokens_removes_all_token_fields():
    hass = _hass()
    entry = _entry({
        CONF_LOGIN: "user",
        CONF_ACCESS_TOKEN: "a",
        CONF_REFRESH_TOKEN: "r",
        CONF_CLIENT_SECRET: "cs",
        CONF_EXPIRES_IN: 43200,
        CONF_TOKEN_OBTAINED_AT: 1.0,
    })
    clear_tokens(hass, entry)
    assert CONF_ACCESS_TOKEN not in entry.data
    assert CONF_REFRESH_TOKEN not in entry.data
    assert CONF_CLIENT_SECRET not in entry.data
    assert CONF_EXPIRES_IN not in entry.data
    assert CONF_TOKEN_OBTAINED_AT not in entry.data
    assert entry.data[CONF_LOGIN] == "user"


def test_clear_tokens_preserves_non_token_fields():
    hass = _hass()
    entry = _entry({CONF_LOGIN: "user", "base_url": "https://example.com"})
    clear_tokens(hass, entry)
    assert entry.data[CONF_LOGIN] == "user"
    assert entry.data["base_url"] == "https://example.com"
