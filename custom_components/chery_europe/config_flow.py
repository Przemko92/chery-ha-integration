from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CODE,
    CONF_LOGIN,
    CONF_PIN,
    CONF_POLL_CHARGING,
    CONF_POLL_HV,
    CONF_POLL_NORMAL,
    DEFAULT_BASE_URL,
    DEFAULT_POLL_CHARGING_MIN,
    DEFAULT_POLL_HV_MIN,
    DEFAULT_POLL_NORMAL_MIN,
    DOMAIN,
)
from .exceptions import (
    CheryEuropeAuthError,
    CheryEuropeConnectionError,
    CheryEuropeRateLimitError,
    CheryEuropeTimeoutError,
)
from .token_storage import token_data_from_response

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOGIN): str,
    }
)

STEP_CODE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CODE): str,
    }
)

STEP_PIN_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PIN): cv.string,
    }
)


class CheryEuropeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Chery Europe."""

    VERSION = 1
    _reauth_entry_data: dict[str, Any] | None = None
    _email: str | None = None
    _client_secret: str | None = None
    _base_url: str = DEFAULT_BASE_URL
    _client_id: str | None = None
    _token_data: dict[str, Any] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlow:
        return CheryEuropeOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_LOGIN].strip()
            errors = await self._async_send_code(email)
            if not errors:
                return await self.async_step_code()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the emailed OTP and mint tokens."""
        errors: dict[str, str] = {}
        email = self._email
        if email is None:
            return await self.async_step_user()

        if user_input is not None:
            code = user_input[CONF_CODE].strip()
            from .auth import CheryEuropeAuth

            session = async_create_clientsession(self.hass)
            auth = CheryEuropeAuth(
                session,
                base_url=self._base_url,
                client_id=self._client_id,
            )

            try:
                response = await auth.login(email, code)
            except CheryEuropeAuthError:
                errors["base"] = "invalid_auth"
            except (CheryEuropeConnectionError, CheryEuropeTimeoutError):
                errors["base"] = "cannot_connect"
            except CheryEuropeRateLimitError:
                errors["base"] = "rate_limit"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Chery Europe login")
                errors["base"] = "unknown"
            else:
                token_data = token_data_from_response(response, self._client_secret)
                if self.source == SOURCE_REAUTH:
                    new_data = {
                        **(self._reauth_entry_data or {}),
                        CONF_LOGIN: email,
                        **token_data,
                    }
                    await self.async_set_unique_id(email)
                    self._abort_if_unique_id_configured(updates=new_data)
                    return self.async_abort(reason="reauth_successful")

                await self.async_set_unique_id(email)
                self._abort_if_unique_id_configured()
                self._token_data = token_data
                return await self.async_step_pin()

        return self.async_show_form(
            step_id="code",
            data_schema=STEP_CODE_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"email": email},
        )

    async def async_step_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the vehicle control PIN used for remote commands."""
        email = self._email
        token_data = self._token_data
        if email is None or token_data is None:
            return await self.async_step_user()

        if user_input is not None:
            return self.async_create_entry(
                title=f"Chery Europe {email}",
                data={
                    CONF_LOGIN: email,
                    **token_data,
                },
                options={CONF_PIN: user_input[CONF_PIN].strip()},
            )

        return self.async_show_form(
            step_id="pin",
            data_schema=STEP_PIN_DATA_SCHEMA,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start reauthentication without auto-sending a code."""
        self._reauth_entry_data = entry_data or {}
        self._email = (self._reauth_entry_data or {}).get(CONF_LOGIN)
        self._base_url = (self._reauth_entry_data or {}).get(
            CONF_BASE_URL, DEFAULT_BASE_URL
        )
        self._client_id = (self._reauth_entry_data or {}).get(CONF_CLIENT_ID)
        self._client_secret = (self._reauth_entry_data or {}).get(CONF_CLIENT_SECRET)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explicitly send a new OTP during reauth, then collect the code."""
        if self.source != SOURCE_REAUTH:
            return await self.async_step_user(user_input)

        errors: dict[str, str] = {}
        known_email = self._email

        if user_input is not None:
            email = known_email or user_input[CONF_LOGIN].strip()
            errors = await self._async_send_code(email)
            if not errors:
                return await self.async_step_code()

        if known_email:
            schema = vol.Schema({})
        else:
            schema = vol.Schema({vol.Required(CONF_LOGIN): str})

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )

    async def _async_send_code(self, email: str) -> dict[str, str]:
        """Send login code; return error map (empty on success)."""
        from .auth import CheryEuropeAuth

        session = async_create_clientsession(self.hass)
        auth = CheryEuropeAuth(
            session,
            base_url=self._base_url,
            client_id=self._client_id,
        )

        try:
            env_config = await auth.fetch_env_config()
            self._client_secret = env_config.client_secret or self._client_secret
        except (
            CheryEuropeConnectionError,
            CheryEuropeTimeoutError,
            CheryEuropeRateLimitError,
        ):
            _LOGGER.debug("Env bootstrap failed; continuing with send-code")

        try:
            await auth.send_mail_code(email)
        except CheryEuropeAuthError as exc:
            message = str(exc).lower()
            if "captcha" in message:
                return {"base": "captcha_failed"}
            return {"base": "otp_send_failed"}
        except ImportError as exc:
            _LOGGER.error("Missing dependency for Chery Europe login: %s", exc)
            return {"base": "otp_send_failed"}
        except (CheryEuropeConnectionError, CheryEuropeTimeoutError):
            return {"base": "cannot_connect"}
        except CheryEuropeRateLimitError:
            return {"base": "rate_limit"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error while sending Chery Europe login code")
            return {"base": "unknown"}

        self._email = email
        return {}


class CheryEuropeOptionsFlowHandler(OptionsFlow):
    """Handle Chery Europe options such as the vehicle control PIN."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options or {}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PIN,
                        default=options.get(CONF_PIN, ""),
                    ): cv.string,
                    vol.Optional(
                        CONF_POLL_NORMAL,
                        default=options.get(CONF_POLL_NORMAL, DEFAULT_POLL_NORMAL_MIN),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
                    vol.Optional(
                        CONF_POLL_CHARGING,
                        default=options.get(
                            CONF_POLL_CHARGING, DEFAULT_POLL_CHARGING_MIN
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
                    vol.Optional(
                        CONF_POLL_HV,
                        default=options.get(CONF_POLL_HV, DEFAULT_POLL_HV_MIN),
                    ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
                }
            ),
        )
