from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.core_config import Config
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CLIENT_ID,
    DEFAULT_BASE_URL,
    DEFAULT_CHANNEL_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TSP_HOST,
    PLATFORMS,
)
from .exceptions import (
    CheryEuropeConnectionError,
    CheryEuropeRateLimitError,
    CheryEuropeTimeoutError,
)
from .token_storage import read_client_secret, read_tokens

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: Config) -> bool:
    """Set up the Chery Europe integration."""
    from .services import async_setup_services

    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Chery Europe from a config entry."""
    from .api import CheryEuropeApi
    from .auth import CheryEuropeAuth
    from .coordinator import CheryEuropeDataUpdateCoordinator

    access_token, refresh_token = read_tokens(entry)
    if not access_token:
        raise ConfigEntryAuthFailed("Missing Chery Europe access token")

    client_id = entry.data.get(CONF_CLIENT_ID)
    client_secret = read_client_secret(entry)

    session = async_get_clientsession(hass)
    auth = CheryEuropeAuth(
        session,
        base_url=DEFAULT_BASE_URL,
        client_id=client_id,
        client_secret=client_secret,
    )
    auth.set_tokens(access_token, refresh_token)

    # Discover OAuth client_id/client_secret/channel at runtime. Vehicle API
    # calls always go through the public EU gateway, not the tspconsole host
    # returned in defaultEnv.domain.
    channel_id = DEFAULT_CHANNEL_ID
    tsp_host = DEFAULT_TSP_HOST
    try:
        env_config = await auth.fetch_env_config()
        if env_config.channel_id:
            channel_id = env_config.channel_id
        if env_config.domain:
            tsp_host = env_config.domain.rstrip("/")
    except (
        CheryEuropeConnectionError,
        CheryEuropeTimeoutError,
        CheryEuropeRateLimitError,
    ):
        _LOGGER.warning(
            "Chery Europe env bootstrap failed; using fallback channel id and TSP host"
        )

    api = CheryEuropeApi(
        auth,
        session,
        base_url=DEFAULT_BASE_URL,
        channel_id=channel_id,
        tsp_host=tsp_host,
    )
    coordinator = CheryEuropeDataUpdateCoordinator(
        hass, api, entry, DEFAULT_SCAN_INTERVAL
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await coordinator.async_start_live_updates()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply polling option changes without reloading the whole integration."""
    coordinator = entry.runtime_data
    if coordinator is None:
        return
    coordinator.update_poll_options(entry.options)
    if coordinator.data is not None:
        coordinator._apply_scan_interval(coordinator.data)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Chery Europe config entry."""
    coordinator = entry.runtime_data
    await coordinator.async_stop_live_updates()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    _LOGGER.debug("Chery Europe config entry migration check for version %s", entry.version)
    return True
