# pyright: reportAttributeAccessIssue=false, reportTypedDictNotRequiredAccess=false, reportMissingImports=false
from unittest.mock import AsyncMock, Mock, patch

import pytest

pytest.importorskip("homeassistant")

from homeassistant.config_entries import SOURCE_REAUTH

from custom_components.chery_europe.config_flow import CheryEuropeConfigFlow
from custom_components.chery_europe.const import (
    CONF_ACCESS_TOKEN,
    CONF_AREA_CODE,
    CONF_ASK_FOR_PIN,
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CODE,
    CONF_EXPIRES_IN,
    CONF_LOGIN,
    CONF_LOGIN_METHOD,
    CONF_PHONE,
    CONF_PIN,
    CONF_PIN_CONFIRM,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_OBTAINED_AT,
    DEFAULT_BASE_URL,
    LOGIN_METHOD_EMAIL,
    LOGIN_METHOD_SMS,
)
from custom_components.chery_europe.exceptions import CheryEuropeAuthError
from custom_components.chery_europe.types.auth_models import AuthResponse
from custom_components.chery_europe.types.env_models import EnvConfig

# Synthetic placeholders — not real numbers (PHONE_PLACEHOLDER).
_PHONE = "500123456"  # PHONE_PLACEHOLDER
_AREA = "48"


def _env_config():
    return EnvConfig.from_dict({
        "data": {
            "clientId": "appCheryLionCloud",
            "clientSecret": "D5HkR0Z1yX8cCM8MNeMw2AC9",
            "domain": "https://tspconsole-eu.cheryinternational.com",
        }
    })


def _auth_response(access_token="demo_token", refresh_token="demo_refresh"):
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=3600,
        token_type="Bearer",
    )


def _flow():
    flow = CheryEuropeConfigFlow()
    flow.hass = Mock()
    flow.hass.config.path = Mock(return_value="/tmp/chery_tls_client.txt")
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()
    flow.async_show_form = Mock(side_effect=lambda **kwargs: {"type": "form", **kwargs})
    flow.async_show_menu = Mock(side_effect=lambda **kwargs: {"type": "menu", **kwargs})
    flow.async_create_entry = Mock(side_effect=lambda **kwargs: {"type": "create_entry", **kwargs})
    flow.async_abort = Mock(side_effect=lambda **kwargs: {"type": "abort", **kwargs})
    flow.add_suggested_values_to_schema = Mock(side_effect=lambda schema, values: schema)
    return flow


@pytest.mark.asyncio
async def test_config_flow_user_shows_login_menu():
    flow = _flow()
    result = await flow.async_step_user()
    assert result["type"] == "menu"
    assert result["step_id"] == "user"
    assert result["menu_options"] == ["login_email", "login_phone"]


@pytest.mark.asyncio
async def test_config_flow_email_sends_code_then_creates_entry():
    flow = _flow()
    login = AsyncMock(return_value=_auth_response())
    send_mail_code = AsyncMock()
    env = _env_config()

    with (
        patch("custom_components.chery_europe.config_flow.async_create_clientsession"),
        patch("custom_components.chery_europe.auth.CheryEuropeAuth") as auth_cls,
    ):
        auth_cls.return_value.send_mail_code = send_mail_code
        auth_cls.return_value.login = login
        auth_cls.return_value.fetch_env_config = AsyncMock(return_value=env)

        result = await flow.async_step_login_email({CONF_LOGIN: "driver@example.com"})
        assert result["type"] == "form"
        assert result["step_id"] == "code"
        send_mail_code.assert_awaited_once_with("driver@example.com")

        result = await flow.async_step_code({CONF_CODE: "123456"})
        assert result["type"] == "form"
        assert result["step_id"] == "pin"

        result = await flow.async_step_pin(
            {CONF_PIN: "9876", CONF_PIN_CONFIRM: "9876"}
        )

    assert result["type"] == "create_entry"
    assert result["title"] == "Chery Europe driver@example.com"
    assert result["data"][CONF_LOGIN] == "driver@example.com"
    assert result["data"][CONF_LOGIN_METHOD] == LOGIN_METHOD_EMAIL
    assert result["data"][CONF_ACCESS_TOKEN] == "demo_token"
    assert result["data"][CONF_REFRESH_TOKEN] == "demo_refresh"
    assert result["data"][CONF_CLIENT_SECRET] == "D5HkR0Z1yX8cCM8MNeMw2AC9"
    assert result["data"][CONF_EXPIRES_IN] == 3600
    assert isinstance(result["data"][CONF_TOKEN_OBTAINED_AT], float)
    assert result["options"] == {CONF_PIN: "9876", CONF_ASK_FOR_PIN: False}
    login.assert_awaited_once_with("driver@example.com", "123456")
    flow.async_set_unique_id.assert_awaited_once_with("driver@example.com")
    flow._abort_if_unique_id_configured.assert_called_once_with()


@pytest.mark.asyncio
async def test_config_flow_sms_sends_code_then_creates_entry():
    flow = _flow()
    login_mobile = AsyncMock(return_value=_auth_response())
    send_sms_code = AsyncMock()
    env = _env_config()

    with (
        patch("custom_components.chery_europe.config_flow.async_create_clientsession"),
        patch("custom_components.chery_europe.auth.CheryEuropeAuth") as auth_cls,
    ):
        auth_cls.return_value.send_sms_code = send_sms_code
        auth_cls.return_value.login_mobile = login_mobile
        auth_cls.return_value.fetch_env_config = AsyncMock(return_value=env)

        result = await flow.async_step_login_phone(
            {CONF_PHONE: _PHONE, CONF_AREA_CODE: _AREA}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "code"
        send_sms_code.assert_awaited_once()
        assert send_sms_code.await_args.args[:2] == (_PHONE, _AREA)

        result = await flow.async_step_code({CONF_CODE: "123456"})
        assert result["type"] == "form"
        assert result["step_id"] == "pin"

        result = await flow.async_step_pin(
            {CONF_PIN: "9876", CONF_PIN_CONFIRM: "9876"}
        )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_PHONE] == _PHONE
    assert result["data"][CONF_AREA_CODE] == _AREA
    assert result["data"][CONF_LOGIN_METHOD] == LOGIN_METHOD_SMS
    assert result["data"][CONF_LOGIN] == f"{_PHONE}_{_AREA}"
    assert "+48 ***3456" in result["title"]
    login_mobile.assert_awaited_once_with(_PHONE, _AREA, "123456")
    flow.async_set_unique_id.assert_awaited_once_with(f"{_PHONE}_{_AREA}")


@pytest.mark.asyncio
async def test_config_flow_phone_invalid_shows_error():
    flow = _flow()
    result = await flow.async_step_login_phone(
        {CONF_PHONE: "12", CONF_AREA_CODE: _AREA}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "login_phone"
    assert result["errors"] == {"base": "phone_invalid"}


@pytest.mark.asyncio
async def test_config_flow_pin_step_can_enable_ask_for_pin():
    flow = _flow()
    flow._email = "driver@example.com"
    flow._login_method = LOGIN_METHOD_EMAIL
    flow._token_data = {
        CONF_ACCESS_TOKEN: "demo_token",
        CONF_REFRESH_TOKEN: "demo_refresh",
        CONF_CLIENT_SECRET: "secret",
        CONF_EXPIRES_IN: 3600,
        CONF_TOKEN_OBTAINED_AT: 1.0,
    }

    result = await flow.async_step_pin(
        {CONF_PIN: "9876", CONF_PIN_CONFIRM: "9876", CONF_ASK_FOR_PIN: True}
    )

    assert result["type"] == "create_entry"
    assert result["options"] == {CONF_PIN: "9876", CONF_ASK_FOR_PIN: True}


@pytest.mark.asyncio
async def test_config_flow_pin_mismatch_shows_error():
    flow = _flow()
    flow._email = "driver@example.com"
    flow._login_method = LOGIN_METHOD_EMAIL
    flow._token_data = {
        CONF_ACCESS_TOKEN: "demo_token",
        CONF_REFRESH_TOKEN: "demo_refresh",
        CONF_CLIENT_SECRET: "secret",
        CONF_EXPIRES_IN: 3600,
        CONF_TOKEN_OBTAINED_AT: 1.0,
    }

    result = await flow.async_step_pin(
        {CONF_PIN: "9876", CONF_PIN_CONFIRM: "0000"}
    )

    assert result["type"] == "form"
    assert result["step_id"] == "pin"
    assert result["errors"] == {CONF_PIN_CONFIRM: "pin_mismatch"}
    flow.async_create_entry.assert_not_called()


@pytest.mark.asyncio
async def test_config_flow_otp_send_failed_shows_error():
    flow = _flow()

    with (
        patch("custom_components.chery_europe.config_flow.async_create_clientsession"),
        patch("custom_components.chery_europe.auth.CheryEuropeAuth") as auth_cls,
    ):
        auth_cls.return_value.fetch_env_config = AsyncMock()
        auth_cls.return_value.send_mail_code = AsyncMock(
            side_effect=CheryEuropeAuthError("Failed to send login code")
        )
        result = await flow.async_step_login_email({CONF_LOGIN: "driver@example.com"})

    assert result["type"] == "form"
    assert result["step_id"] == "login_email"
    assert result["errors"] == {"base": "otp_send_failed"}
    flow.async_set_unique_id.assert_not_called()


@pytest.mark.asyncio
async def test_config_flow_invalid_code_shows_error():
    flow = _flow()
    flow._email = "driver@example.com"
    flow._login_method = LOGIN_METHOD_EMAIL
    flow._client_secret = "D5HkR0Z1yX8cCM8MNeMw2AC9"

    with (
        patch("custom_components.chery_europe.config_flow.async_create_clientsession"),
        patch("custom_components.chery_europe.auth.CheryEuropeAuth") as auth_cls,
    ):
        auth_cls.return_value.login = AsyncMock(side_effect=CheryEuropeAuthError("bad"))
        result = await flow.async_step_code({CONF_CODE: "000000"})

    assert result["type"] == "form"
    assert result["step_id"] == "code"
    assert result["errors"] == {"base": "invalid_auth"}
    flow.async_set_unique_id.assert_not_called()


@pytest.mark.asyncio
async def test_reauth_flow_sends_code_then_updates_tokens():
    flow = _flow()
    flow.context = {"source": SOURCE_REAUTH}
    env = _env_config()
    entry_data = {
        CONF_LOGIN: "driver@example.com",
        CONF_LOGIN_METHOD: LOGIN_METHOD_EMAIL,
        CONF_BASE_URL: DEFAULT_BASE_URL,
        CONF_CLIENT_ID: None,
        CONF_ACCESS_TOKEN: "old",
    }

    result = await flow.async_step_reauth(entry_data)

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    with (
        patch("custom_components.chery_europe.config_flow.async_create_clientsession"),
        patch("custom_components.chery_europe.auth.CheryEuropeAuth") as auth_cls,
    ):
        auth_cls.return_value.fetch_env_config = AsyncMock(return_value=env)
        auth_cls.return_value.send_mail_code = AsyncMock()
        auth_cls.return_value.login = AsyncMock(return_value=_auth_response("new", "refresh"))

        result = await flow.async_step_reauth_confirm({})
        assert result["type"] == "form"
        assert result["step_id"] == "code"

        result = await flow.async_step_code({CONF_CODE: "654321"})

    assert result == {"type": "abort", "reason": "reauth_successful"}
    flow.async_set_unique_id.assert_awaited_once_with("driver@example.com")
    updates = flow._abort_if_unique_id_configured.call_args.kwargs["updates"]
    assert updates[CONF_LOGIN] == "driver@example.com"
    assert updates[CONF_ACCESS_TOKEN] == "new"
    assert updates[CONF_REFRESH_TOKEN] == "refresh"
    assert updates[CONF_CLIENT_SECRET] == "D5HkR0Z1yX8cCM8MNeMw2AC9"
    assert updates[CONF_EXPIRES_IN] == 3600
    assert isinstance(updates[CONF_TOKEN_OBTAINED_AT], float)


@pytest.mark.asyncio
async def test_reauth_flow_sms_uses_send_sms_code():
    flow = _flow()
    flow.context = {"source": SOURCE_REAUTH}
    env = _env_config()
    entry_data = {
        CONF_LOGIN: f"{_PHONE}_{_AREA}",
        CONF_PHONE: _PHONE,
        CONF_AREA_CODE: _AREA,
        CONF_LOGIN_METHOD: LOGIN_METHOD_SMS,
        CONF_BASE_URL: DEFAULT_BASE_URL,
        CONF_ACCESS_TOKEN: "old",
    }

    await flow.async_step_reauth(entry_data)

    with (
        patch("custom_components.chery_europe.config_flow.async_create_clientsession"),
        patch("custom_components.chery_europe.auth.CheryEuropeAuth") as auth_cls,
    ):
        auth_cls.return_value.fetch_env_config = AsyncMock(return_value=env)
        auth_cls.return_value.send_sms_code = AsyncMock()
        auth_cls.return_value.login_mobile = AsyncMock(
            return_value=_auth_response("new", "refresh")
        )

        result = await flow.async_step_reauth_confirm({})
        assert result["step_id"] == "code"
        auth_cls.return_value.send_sms_code.assert_awaited_once()

        result = await flow.async_step_code({CONF_CODE: "654321"})

    assert result == {"type": "abort", "reason": "reauth_successful"}
    flow.async_set_unique_id.assert_awaited_once_with(f"{_PHONE}_{_AREA}")
