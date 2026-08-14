# pyright: reportMissingImports=false
import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

pytest.importorskip("homeassistant")

from custom_components.chery_europe.auth import CheryEuropeAuth
from custom_components.chery_europe.const import DEFAULT_ENV_URL
from custom_components.chery_europe.exceptions import (
    CheryEuropeConnectionError,
    CheryEuropeRateLimitError,
    CheryEuropeTimeoutError,
)
from custom_components.chery_europe.types.env_models import EnvConfig


def _env_payload():
    return {
        "code": 0,
        "msg": "Operation successful",
        "key": "operation.successful",
        "data": {
            "id": "1932044841126526978",
            "name": "CHERY",
            "country": "1",
            "tspEnv": "0",
            "clientId": "appCheryLionCloud",
            "clientSecret": "D5HkR0Z1yX8cCM8MNeMw2AC9",
            "domain": "https://tspconsole-eu.cheryinternational.com",
            "channelId": 5,
            "mapType": "here",
            "status": 1,
            "tenantId": "300001",
        },
        "ok": True,
    }


def _mock_get(response_status=200, response_json=None, side_effect=None):
    """Return a MagicMock standing in for ``session.get``.

    ``session.get(...)`` returns an async context manager whose ``__aenter__``
    yields a response object exposing ``.status`` and an awaitable ``.json()``.
    """
    response = MagicMock()
    response.status = response_status
    response.json = AsyncMock(return_value=response_json or {})

    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=response)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock(spec=aiohttp.ClientSession)
    if side_effect is not None:
        session.get = MagicMock(side_effect=side_effect)
    else:
        session.get = MagicMock(return_value=context_manager)
    return session, response


@pytest.mark.asyncio
async def test_fetch_env_config_parses_default_env_and_sets_base_url():
    session, _ = _mock_get(200, _env_payload())
    auth = CheryEuropeAuth(session)

    env = await auth.fetch_env_config()

    assert isinstance(env, EnvConfig)
    assert env.id == "1932044841126526978"
    assert env.name == "CHERY"
    assert env.country == "1"
    assert env.tsp_env == "0"
    assert env.client_id == "appCheryLionCloud"
    assert env.client_secret == "D5HkR0Z1yX8cCM8MNeMw2AC9"
    assert env.domain == "https://tspconsole-eu.cheryinternational.com"
    assert env.channel_id == 5
    assert env.map_type == "here"
    assert env.status == 1
    assert env.tenant_id == "300001"

    assert auth.env_config is env
    assert auth._base_url == "https://tspconsole-eu.cheryinternational.com"
    session.get.assert_called_once()
    called_url = session.get.call_args.args[0]
    assert called_url == DEFAULT_ENV_URL


@pytest.mark.asyncio
async def test_fetch_env_config_uses_custom_env_url():
    session, _ = _mock_get(200, _env_payload())
    auth = CheryEuropeAuth(session)

    await auth.fetch_env_config(env_url="https://custom.example.com/env")

    called_url = session.get.call_args.args[0]
    assert called_url == "https://custom.example.com/env"


@pytest.mark.asyncio
async def test_fetch_env_config_accepts_flat_payload_without_data_envelope():
    flat = _env_payload()["data"]
    session, _ = _mock_get(200, flat)
    auth = CheryEuropeAuth(session)

    env = await auth.fetch_env_config()

    assert env.client_id == "appCheryLionCloud"
    assert env.tenant_id == "300001"


@pytest.mark.asyncio
async def test_fetch_env_config_rate_limit_raises():
    session, _ = _mock_get(429, {})
    auth = CheryEuropeAuth(session)

    with pytest.raises(CheryEuropeRateLimitError):
        await auth.fetch_env_config()


@pytest.mark.asyncio
async def test_fetch_env_config_server_error_raises_connection_error():
    session, _ = _mock_get(500, {})
    auth = CheryEuropeAuth(session)

    with pytest.raises(CheryEuropeConnectionError):
        await auth.fetch_env_config()


@pytest.mark.asyncio
async def test_fetch_env_config_non_dict_body_raises_connection_error():
    session, _ = _mock_get(200, ["not", "a", "dict"])
    auth = CheryEuropeAuth(session)

    with pytest.raises(CheryEuropeConnectionError):
        await auth.fetch_env_config()


@pytest.mark.asyncio
async def test_fetch_env_config_timeout_raises_timeout_error():
    session, _ = _mock_get(side_effect=asyncio.TimeoutError())
    auth = CheryEuropeAuth(session)

    with pytest.raises(CheryEuropeTimeoutError):
        await auth.fetch_env_config()


@pytest.mark.asyncio
async def test_fetch_env_config_connection_error_raises_connection_error():
    session, _ = _mock_get(side_effect=aiohttp.ClientConnectionError("boom"))
    auth = CheryEuropeAuth(session)

    with pytest.raises(CheryEuropeConnectionError):
        await auth.fetch_env_config()


@pytest.mark.asyncio
async def test_fetch_env_config_client_error_raises_connection_error():
    session, _ = _mock_get(side_effect=aiohttp.ClientError("boom"))
    auth = CheryEuropeAuth(session)

    with pytest.raises(CheryEuropeConnectionError):
        await auth.fetch_env_config()


@pytest.mark.asyncio
async def test_fetch_env_config_does_not_send_credentials():
    session, _ = _mock_get(200, _env_payload())
    auth = CheryEuropeAuth(session)
    auth.access_token = "preexisting-token"

    await auth.fetch_env_config()

    kwargs = session.get.call_args.kwargs
    headers = kwargs.get("headers", {})
    assert "Authorization" not in headers
    assert "User-Agent" in headers


def test_env_config_is_frozen():
    env = EnvConfig.from_dict(_env_payload())
    with pytest.raises(Exception):
        env.client_id = "mutated"  # type: ignore[misc]