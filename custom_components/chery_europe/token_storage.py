from __future__ import annotations

import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CLIENT_SECRET,
    CONF_EXPIRES_IN,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_OBTAINED_AT,
)
from .types.auth_models import AuthResponse

#: Token-related keys managed by these helpers.
_TOKEN_KEYS = {
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_CLIENT_SECRET,
    CONF_EXPIRES_IN,
    CONF_TOKEN_OBTAINED_AT,
}


def read_tokens(entry: ConfigEntry) -> tuple[str | None, str | None]:
    """Read access and refresh tokens from a config entry."""
    return entry.data.get(CONF_ACCESS_TOKEN), entry.data.get(CONF_REFRESH_TOKEN)


def read_client_secret(entry: ConfigEntry) -> str | None:
    """Read the OAuth2 client_secret from a config entry."""
    return entry.data.get(CONF_CLIENT_SECRET)


def read_token_expiry(entry: ConfigEntry) -> tuple[int, float | None]:
    """Return ``(expires_in, token_obtained_at)`` from a config entry.

    ``token_obtained_at`` is ``None`` when the entry was created before expiry
    metadata was persisted (older installs).
    """
    expires_in = entry.data.get(CONF_EXPIRES_IN)
    try:
        expires_in_int = int(expires_in) if expires_in is not None else 0
    except (TypeError, ValueError):
        expires_in_int = 0

    obtained = entry.data.get(CONF_TOKEN_OBTAINED_AT)
    try:
        obtained_at = float(obtained) if obtained is not None else None
    except (TypeError, ValueError):
        obtained_at = None
    return expires_in_int, obtained_at


def token_data_from_response(
    response: AuthResponse,
    client_secret: str | None = None,
    *,
    obtained_at: float | None = None,
) -> dict[str, str | int | float]:
    """Return ConfigEntry-safe token fields from an auth response.

    ``client_secret`` is included only when explicitly provided so that
    callers without an :class:`EnvConfig` do not clobber a previously
    stored value with ``None``.

    ``expires_in`` and ``token_obtained_at`` are always written so a later
    reload can schedule proactive refresh without waiting for HTTP 401.
    """
    data: dict[str, str | int | float] = {
        CONF_ACCESS_TOKEN: response.access_token,
        CONF_REFRESH_TOKEN: response.refresh_token,
        CONF_EXPIRES_IN: int(response.expires_in or 0),
        CONF_TOKEN_OBTAINED_AT: float(
            time.time() if obtained_at is None else obtained_at
        ),
    }
    if client_secret is not None:
        data[CONF_CLIENT_SECRET] = client_secret
    return data


def write_tokens(
    hass: HomeAssistant,
    entry: ConfigEntry,
    response: AuthResponse,
    client_secret: str | None = None,
    *,
    obtained_at: float | None = None,
) -> None:
    """Persist tokens in ConfigEntry.data without exposing sensitive values."""
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            **token_data_from_response(
                response, client_secret, obtained_at=obtained_at
            ),
        },
    )


def clear_tokens(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove token fields from ConfigEntry.data."""
    hass.config_entries.async_update_entry(
        entry,
        data={
            key: value
            for key, value in entry.data.items()
            if key not in _TOKEN_KEYS
        },
    )
