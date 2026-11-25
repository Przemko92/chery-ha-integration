from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_CLIENT_ID,
    CONF_VINS,
    DEFAULT_BASE_URL,
    DEFAULT_CHANNEL_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TSP_HOST,
    DOMAIN,
    PLATFORMS,
)
from .exceptions import (
    CheryEuropeConnectionError,
    CheryEuropeRateLimitError,
    CheryEuropeTimeoutError,
)
from .token_storage import read_client_secret, read_token_expiry, read_tokens, write_tokens
from .types.auth_models import AuthResponse

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Chery Europe integration."""
    from .services import async_setup_services

    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Chery Europe from a config entry."""
    from .api import CheryEuropeApi
    from .auth import CheryEuropeAuth
    from .coordinator import CheryEuropeDataUpdateCoordinator, CheryEuropeRuntime
    from .entity import vehicle_slot

    access_token, refresh_token = read_tokens(entry)
    if not access_token:
        raise ConfigEntryAuthFailed("Missing Chery Europe access token")

    client_id = entry.data.get(CONF_CLIENT_ID)
    client_secret = read_client_secret(entry)
    expires_in, obtained_at = read_token_expiry(entry)

    session = async_get_clientsession(hass)
    auth = CheryEuropeAuth(
        session,
        base_url=DEFAULT_BASE_URL,
        client_id=client_id,
        client_secret=client_secret,
    )
    auth.set_tokens(
        access_token,
        refresh_token,
        expires_in=expires_in,
        obtained_at=obtained_at,
    )

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

    def _persist_tokens(response: AuthResponse) -> None:
        # Refresh tokens rotate on every use; losing them forces a new OTP.
        write_tokens(
            hass,
            entry,
            response,
            client_secret=auth._resolve_client_secret(),
            obtained_at=auth.token_obtained_at,
        )

    api = CheryEuropeApi(
        auth,
        session,
        base_url=DEFAULT_BASE_URL,
        channel_id=channel_id,
        tsp_host=tsp_host,
        on_tokens_updated=_persist_tokens,
    )
    vins = [str(vin) for vin in (entry.data.get(CONF_VINS) or []) if vin]
    if len(vins) <= 1:
        coordinators = [
            CheryEuropeDataUpdateCoordinator(
                hass,
                api,
                entry,
                DEFAULT_SCAN_INTERVAL,
                vin=vins[0] if vins else None,
            )
        ]
    else:
        coordinators = []
        for index, vin in enumerate(vins):
            slot = None if index == 0 else vehicle_slot(vin)
            coordinators.append(
                CheryEuropeDataUpdateCoordinator(
                    hass,
                    api,
                    entry,
                    DEFAULT_SCAN_INTERVAL,
                    vin=vin,
                    entity_slot=slot,
                    device_id=entry.entry_id if slot is None else f"{entry.entry_id}_{slot}",
                    rename_entry=False,
                    owns_account_session=index == 0,
                )
            )
    runtime = CheryEuropeRuntime(coordinators)
    for coordinator in coordinators:
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = runtime
    from .entity import (
        async_drop_vin_from_names,
        async_move_to_controls,
        async_remove_legacy_entities,
        async_rename_entity_ids,
    )

    async_remove_legacy_entities(hass, entry)
    async_rename_entity_ids(hass, entry)
    async_move_to_controls(hass, entry)
    for coordinator in coordinators:
        vin = coordinator.data.vin if coordinator.data is not None else None
        async_drop_vin_from_names(hass, entry, vin)

    await runtime.async_start_live_updates()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply polling option changes without reloading the whole integration."""
    runtime = entry.runtime_data
    if runtime is None:
        return
    runtime.update_poll_options(entry.options)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Chery Europe config entry."""
    runtime = entry.runtime_data
    await runtime.async_stop_live_updates()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries."""
    _LOGGER.debug("Chery Europe config entry migration check for version %s", entry.version)
    return True
