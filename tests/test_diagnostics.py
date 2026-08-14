# pyright: reportAttributeAccessIssue=false
"""Diagnostics redaction tests for the Chery Europe integration.

Asserts that ``async_get_config_entry_diagnostics`` redacts every sensitive
field (tokens, PIN, VIN, login, location, account_id, password, code, client_secret
in both snake_case and camelCase forms) from both ``entry.data`` and the
coordinator's ``runtime_data.data`` payload.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.diagnostics import (
    REDACTED,
    async_get_config_entry_diagnostics,
)

# Sensitive keys that MUST be redacted. Covers snake_case, camelCase, and
# no-separator variants of client_secret.
SECRET_DATA = {
    "access_token": "tok-secret",
    "refresh_token": "refresh-secret",
    "client_secret": "cs-snake",
    "clientSecret": "cs-camel",
    "pin": "1234",
    "vin": "VINSECRET",
    "login": "driver@example.com",
    "password": "pw-secret",
    "code": "otp-secret",
    "latitude": 50.123,
    "longitude": 20.456,
    "account_id": "acct-123",
}

# Non-sensitive keys that MUST remain visible (not redacted).
SAFE_DATA = {
    "base_url": "https://tspconsole-eu.cheryinternational.com",
    "client_id": "appCheryLionCloud",
}


def _entry():
    """Build a mocked ConfigEntry with secrets in data and runtime_data."""
    return SimpleNamespace(
        entry_id="test-entry-id",
        data={**SECRET_DATA, **SAFE_DATA},
        runtime_data=SimpleNamespace(
            last_update_success=True,
            last_update_success_time=None,
            data={
                "vehicle": {
                    "vin": "VINSECRET",
                    "latitude": 50.123,
                    "longitude": 20.456,
                    "access_token": "tok-secret",
                    "login": "driver@example.com",
                    "clientSecret": "cs-camel",
                    "model": "eQ7",  # non-sensitive, must stay visible
                },
            },
        ),
    )


@pytest.mark.asyncio
async def test_diagnostics_redacts_all_sensitive_fields():
    """Every secret in entry.data and runtime_data.data is replaced with REDACTED."""
    hass = Mock()
    entry = _entry()

    with patch(
        "custom_components.chery_europe.diagnostics.er.async_get",
        return_value=Mock(),
    ), patch(
        "custom_components.chery_europe.diagnostics.er.async_entries_for_config_entry",
        return_value=[],
    ):
        result = await async_get_config_entry_diagnostics(hass, entry)

    # entry.data secrets redacted
    config_data = result["config_entry_data"]
    for key, value in SECRET_DATA.items():
        assert config_data[key] == REDACTED, f"{key!r} was not redacted (got {config_data[key]!r})"

    # entry.data non-sensitive fields remain visible
    for key, value in SAFE_DATA.items():
        assert config_data[key] == value, f"{key!r} should remain visible (got {config_data[key]!r})"

    # runtime_data.data nested secrets redacted
    vehicle = result["data"]["vehicle"]
    assert vehicle["vin"] == REDACTED
    assert vehicle["latitude"] == REDACTED
    assert vehicle["longitude"] == REDACTED
    assert vehicle["access_token"] == REDACTED
    assert vehicle["login"] == REDACTED
    assert vehicle["clientSecret"] == REDACTED

    # runtime_data.data non-sensitive field remains visible
    assert vehicle["model"] == "eQ7"

    # Top-level non-sensitive diagnostics fields remain visible
    assert result["entry_id"] == "test-entry-id"
    assert result["domain"] == "chery_europe"
    assert result["entity_count"] == 0
    assert result["last_update_success"] is True


@pytest.mark.asyncio
async def test_diagnostics_handles_missing_runtime_data():
    """Diagnostics still works when runtime_data is None (no coordinator yet)."""
    hass = Mock()
    entry = SimpleNamespace(
        entry_id="no-coord-entry",
        data=dict(SECRET_DATA),
        runtime_data=None,
    )

    with patch(
        "custom_components.chery_europe.diagnostics.er.async_get",
        return_value=Mock(),
    ), patch(
        "custom_components.chery_europe.diagnostics.er.async_entries_for_config_entry",
        return_value=[],
    ):
        result = await async_get_config_entry_diagnostics(hass, entry)

    config_data = result["config_entry_data"]
    for key in SECRET_DATA:
        assert config_data[key] == REDACTED, f"{key!r} was not redacted"

    # No coordinator → these default to None
    assert result["data"] is None
    assert result["last_update_success"] is None
