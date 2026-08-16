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
    CONF_AREA_CODE,
    CONF_ASK_FOR_PIN,
    CONF_BASE_URL,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_CODE,
    CONF_LOGIN,
    CONF_LOGIN_METHOD,
    CONF_PHONE,
    CONF_PIN,
    CONF_PIN_CONFIRM,
    CONF_POLL_CHARGING,
    CONF_POLL_HV,
    CONF_POLL_NORMAL,
    DEFAULT_AREA_CODE,
    DEFAULT_BASE_URL,
    DEFAULT_POLL_CHARGING_MIN,
    DEFAULT_POLL_HV_MIN,
    DEFAULT_POLL_NORMAL_MIN,
    DOMAIN,
    LOGIN_METHOD_EMAIL,
    LOGIN_METHOD_SMS,
)
from .exceptions import (
    CheryEuropeAuthError,
    CheryEuropeConnectionError,
    CheryEuropeRateLimitError,
    CheryEuropeTimeoutError,
)
from .phone import mask_phone, normalize_phone
from .token_storage import token_data_from_response

_LOGGER = logging.getLogger(__name__)

STEP_EMAIL_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_LOGIN): str,
    }
)

STEP_PHONE_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PHONE): str,
        vol.Required(CONF_AREA_CODE, default=DEFAULT_AREA_CODE): str,
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
        vol.Required(CONF_PIN_CONFIRM): cv.string,
        vol.Optional(CONF_ASK_FOR_PIN, default=False): cv.boolean,
    }
)


class CheryEuropeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Chery Europe."""

    VERSION = 1
    _reauth_entry_data: dict[str, Any] | None = None
    _email: str | None = None
    _phone: str | None = None
    _area_code: str | None = None
    _login_method: str = LOGIN_METHOD_EMAIL
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
        """Choose email (recommended) or SMS login."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["login_email", "login_phone"],
        )

    async def async_step_login_email(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Recommended path: email OTP."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_LOGIN].strip()
            self._login_method = LOGIN_METHOD_EMAIL
            self._phone = None
            self._area_code = None
            errors = await self._async_send_code(email=email)
            if not errors:
                return await self.async_step_code()

        return self.async_show_form(
            step_id="login_email",
            data_schema=STEP_EMAIL_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_login_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optional path: SMS OTP for phone-registered accounts."""
        errors: dict[str, str] = {}
        schema = STEP_PHONE_DATA_SCHEMA

        if user_input is not None:
            user_input = dict(user_input)
            phone, area = normalize_phone(
                user_input.get(CONF_PHONE), user_input.get(CONF_AREA_CODE)
            )
            if not phone or not area:
                return self.async_show_form(
                    step_id="login_phone",
                    data_schema=self.add_suggested_values_to_schema(schema, user_input),
                    errors={"base": "phone_invalid"},
                )
            self._login_method = LOGIN_METHOD_SMS
            self._email = None
            errors = await self._async_send_code(phone=phone, area_code=area)
            if not errors:
                return await self.async_step_code()
            schema = self.add_suggested_values_to_schema(
                schema, {CONF_PHONE: phone, CONF_AREA_CODE: area}
            )

        return self.async_show_form(
            step_id="login_phone",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the OTP and mint tokens."""
        errors: dict[str, str] = {}
        if not self._has_login_destination():
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
                if self._login_method == LOGIN_METHOD_SMS:
                    assert self._phone is not None and self._area_code is not None
                    response = await auth.login_mobile(
                        self._phone, self._area_code, code
                    )
                else:
                    assert self._email is not None
                    response = await auth.login(self._email, code)
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
                unique_id = self._unique_id()
                account_data = self._account_data()
                if self.source == SOURCE_REAUTH:
                    new_data = {
                        **(self._reauth_entry_data or {}),
                        **account_data,
                        **token_data,
                    }
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured(updates=new_data)
                    return self.async_abort(reason="reauth_successful")

                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                self._token_data = token_data
                return await self.async_step_pin()

        return self.async_show_form(
            step_id="code",
            data_schema=STEP_CODE_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"destination": self._destination_label()},
        )

    async def async_step_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the vehicle control PIN used for remote commands."""
        token_data = self._token_data
        if not self._has_login_destination() or token_data is None:
            return await self.async_step_user()

        errors: dict[str, str] = {}
        if user_input is not None:
            pin = user_input[CONF_PIN].strip()
            confirm = user_input[CONF_PIN_CONFIRM].strip()
            if not pin:
                errors[CONF_PIN] = "pin_required"
            elif pin != confirm:
                errors[CONF_PIN_CONFIRM] = "pin_mismatch"
            else:
                return self.async_create_entry(
                    title=self._entry_title(),
                    data={
                        **self._account_data(),
                        **token_data,
                    },
                    options={
                        CONF_PIN: pin,
                        CONF_ASK_FOR_PIN: bool(user_input.get(CONF_ASK_FOR_PIN, False)),
                    },
                )

        return self.async_show_form(
            step_id="pin",
            data_schema=STEP_PIN_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start reauthentication without auto-sending a code."""
        self._reauth_entry_data = entry_data or {}
        data = self._reauth_entry_data
        self._login_method = data.get(CONF_LOGIN_METHOD) or (
            LOGIN_METHOD_SMS if data.get(CONF_PHONE) else LOGIN_METHOD_EMAIL
        )
        self._email = data.get(CONF_LOGIN) if self._login_method == LOGIN_METHOD_EMAIL else None
        self._phone = data.get(CONF_PHONE)
        self._area_code = data.get(CONF_AREA_CODE)
        if self._login_method == LOGIN_METHOD_EMAIL and not self._email:
            self._email = data.get(CONF_LOGIN)
        self._base_url = data.get(CONF_BASE_URL, DEFAULT_BASE_URL)
        self._client_id = data.get(CONF_CLIENT_ID)
        self._client_secret = data.get(CONF_CLIENT_SECRET)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Explicitly send a new OTP during reauth, then collect the code."""
        if self.source != SOURCE_REAUTH:
            return await self.async_step_user()

        errors: dict[str, str] = {}
        known = self._has_login_destination()

        if user_input is not None:
            if self._login_method == LOGIN_METHOD_SMS:
                phone = self._phone
                area = self._area_code
                if not phone or not area:
                    phone, area = normalize_phone(
                        user_input.get(CONF_PHONE), user_input.get(CONF_AREA_CODE)
                    )
                    if not phone or not area:
                        errors["base"] = "phone_invalid"
                    else:
                        errors = await self._async_send_code(phone=phone, area_code=area)
                else:
                    errors = await self._async_send_code(phone=phone, area_code=area)
            else:
                email = self._email or user_input[CONF_LOGIN].strip()
                errors = await self._async_send_code(email=email)
            if not errors:
                return await self.async_step_code()

        if known:
            schema = vol.Schema({})
        elif self._login_method == LOGIN_METHOD_SMS:
            schema = STEP_PHONE_DATA_SCHEMA
        else:
            schema = STEP_EMAIL_DATA_SCHEMA

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"destination": self._destination_label()},
        )

    def _has_login_destination(self) -> bool:
        if self._login_method == LOGIN_METHOD_SMS:
            return bool(self._phone and self._area_code)
        return bool(self._email)

    def _unique_id(self) -> str:
        if self._login_method == LOGIN_METHOD_SMS:
            return f"{self._phone}_{self._area_code}"
        assert self._email is not None
        return self._email

    def _account_data(self) -> dict[str, Any]:
        if self._login_method == LOGIN_METHOD_SMS:
            assert self._phone is not None and self._area_code is not None
            return {
                CONF_LOGIN: f"{self._phone}_{self._area_code}",
                CONF_PHONE: self._phone,
                CONF_AREA_CODE: self._area_code,
                CONF_LOGIN_METHOD: LOGIN_METHOD_SMS,
            }
        assert self._email is not None
        return {
            CONF_LOGIN: self._email,
            CONF_LOGIN_METHOD: LOGIN_METHOD_EMAIL,
        }

    def _destination_label(self) -> str:
        if self._login_method == LOGIN_METHOD_SMS and self._phone and self._area_code:
            return mask_phone(self._phone, self._area_code)
        return self._email or ""

    def _entry_title(self) -> str:
        if self._login_method == LOGIN_METHOD_SMS and self._phone and self._area_code:
            return f"Chery Europe {mask_phone(self._phone, self._area_code)}"
        return f"Chery Europe {self._email}"

    def _tls_memory_path(self) -> str:
        return self.hass.config.path(f".storage/{DOMAIN}_tls_client.txt")

    async def _async_send_code(
        self,
        *,
        email: str | None = None,
        phone: str | None = None,
        area_code: str | None = None,
    ) -> dict[str, str]:
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
            if phone and area_code:
                await auth.send_sms_code(
                    phone, area_code, memory_path=self._tls_memory_path()
                )
            else:
                assert email is not None
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

        if phone and area_code:
            self._phone = phone
            self._area_code = area_code
            self._login_method = LOGIN_METHOD_SMS
            self._email = None
        else:
            self._email = email
            self._login_method = LOGIN_METHOD_EMAIL
            self._phone = None
            self._area_code = None
        return {}


class CheryEuropeOptionsFlowHandler(OptionsFlow):
    """Handle Chery Europe options such as the vehicle control PIN."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        options = self._config_entry.options or {}
        if user_input is not None:
            data = dict(user_input)
            current = str(options.get(CONF_PIN, "") or "")
            pin = str(data.pop(CONF_PIN, "") or "").strip()
            confirm = str(data.pop(CONF_PIN_CONFIRM, "") or "").strip()
            if pin != current and pin and pin != confirm:
                errors[CONF_PIN_CONFIRM] = "pin_mismatch"
            else:
                if pin:
                    data[CONF_PIN] = pin
                data[CONF_ASK_FOR_PIN] = bool(data.get(CONF_ASK_FOR_PIN, False))
                return self.async_create_entry(title="", data=data)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_PIN,
                        default=options.get(CONF_PIN, ""),
                    ): cv.string,
                    vol.Optional(CONF_PIN_CONFIRM, default=""): cv.string,
                    vol.Optional(
                        CONF_ASK_FOR_PIN,
                        default=options.get(CONF_ASK_FOR_PIN, False),
                    ): cv.boolean,
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
            errors=errors,
        )
