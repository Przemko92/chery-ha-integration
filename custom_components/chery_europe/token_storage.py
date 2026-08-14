from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ACCESS_TOKEN, CONF_CLIENT_SECRET, CONF_REFRESH_TOKEN
from .types.auth_models import AuthResponse

#: Token-related keys managed by these helpers.
_TOKEN_KEYS = {CONF_ACCESS_TOKEN, CONF_REFRESH_TOKEN, CONF_CLIENT_SECRET}


def read_tokens(entry: ConfigEntry) -> tuple[str | None, str | None]:
    """Read access and refresh tokens from a config entry."""
    return entry.data.get(CONF_ACCESS_TOKEN), entry.data.get(CONF_REFRESH_TOKEN)


def read_client_secret(entry: ConfigEntry) -> str | None:
    """Read the OAuth2 client_secret from a config entry."""
    return entry.data.get(CONF_CLIENT_SECRET)


def token_data_from_response(
    response: AuthResponse,
    client_secret: str | None = None,
) -> dict[str, str | int]:
    """Return ConfigEntry-safe token fields from an auth response.

    ``client_secret`` is included only when explicitly provided so that
    callers without an :class:`EnvConfig` do not clobber a previously
    stored value with ``None``.
    """
    data: dict[str, str | int] = {
        CONF_ACCESS_TOKEN: response.access_token,
        CONF_REFRESH_TOKEN: response.refresh_token,
    }
    if client_secret is not None:
        data[CONF_CLIENT_SECRET] = client_secret
    return data


def write_tokens(
    hass: HomeAssistant,
    entry: ConfigEntry,
    response: AuthResponse,
    client_secret: str | None = None,
) -> None:
    """Persist tokens in ConfigEntry.data without exposing sensitive values."""
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, **token_data_from_response(response, client_secret)},
    )


def clear_tokens(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove token fields (access, refresh, client_secret) from ConfigEntry.data."""
    hass.config_entries.async_update_entry(
        entry,
        data={
            key: value
            for key, value in entry.data.items()
            if key not in _TOKEN_KEYS
        },
    )