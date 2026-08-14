import asyncio
import logging
from typing import Any, Mapping

import aiohttp

from .const import (
    DEFAULT_BASE_URL,
    DEFAULT_ENV_URL,
    DEFAULT_LOGIN_ENDPOINT,
    DEFAULT_SEND_MAIL_CODE_ENDPOINT,
    DEFAULT_USER_AGENT,
    HEADER_ACCEPT,
    HEADER_ACCEPT_ENCODING,
    HEADER_ACCEPT_LANGUAGE,
    HEADER_BASIC_AUTH,
    HEADER_CONTENT_TYPE,
    HEADER_FORM_CONTENT_TYPE,
    LOGIN_EMAIL_PREFIX,
    LOGIN_MODULE,
)
from .exceptions import (
    CheryEuropeAuthError,
    CheryEuropeConnectionError,
    CheryEuropeRateLimitError,
    CheryEuropeTimeoutError,
)
from .types.auth_models import AuthResponse
from .types.env_models import EnvConfig

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class CheryEuropeAuth:
    """Authentication client for Chery Europe app API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str = DEFAULT_BASE_URL,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self.access_token: str | None = None
        self.refresh_token_value: str | None = None
        self.env_config: EnvConfig | None = None

    async def fetch_env_config(self, env_url: str = DEFAULT_ENV_URL) -> EnvConfig:
        """Fetch the unauthenticated ``defaultEnv`` bootstrap payload.

        The Chery Europe app calls this endpoint first to discover the active
        TSP domain, OAuth client credentials, tenant and channel. The returned
        :class:`EnvConfig` is cached on ``self.env_config`` and its ``domain``
        becomes the base URL for subsequent login/API calls. No credentials are
        sent and ``client_secret`` is never logged.
        """
        _LOGGER.debug("Chery Europe env bootstrap request: GET %s", env_url)
        headers = {
            "Accept": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        try:
            async with self._session.get(
                env_url,
                timeout=REQUEST_TIMEOUT,
                headers=headers,
            ) as response:
                _LOGGER.debug(
                    "Chery Europe env bootstrap response: status=%s",
                    response.status,
                )
                if response.status == 429:
                    raise CheryEuropeRateLimitError("Rate limit exceeded")
                if response.status >= 400:
                    raise CheryEuropeConnectionError(
                        f"Chery Europe env bootstrap returned status {response.status}"
                    )
                data = await response.json(content_type=None)
                if not isinstance(data, dict):
                    raise CheryEuropeConnectionError(
                        "Unexpected env bootstrap response shape"
                    )
        except asyncio.TimeoutError as exc:
            raise CheryEuropeTimeoutError(
                "Env bootstrap request timed out"
            ) from exc
        except aiohttp.ClientConnectionError as exc:
            raise CheryEuropeConnectionError(
                "Unable to connect to Chery Europe env bootstrap"
            ) from exc
        except aiohttp.ClientError as exc:
            raise CheryEuropeConnectionError(
                "Chery Europe env bootstrap HTTP error"
            ) from exc

        env_config = EnvConfig.from_dict(data)
        self.env_config = env_config
        if env_config.domain:
            self._base_url = env_config.domain.rstrip("/")
        return env_config

    async def send_mail_code(self, email: str) -> None:
        """Solve AJ-Captcha and request an email OTP for APP-LOGIN.

        Uses the v2 marketing endpoint which accepts AJ-Captcha
        ``captchaVerification`` tokens. The v3 endpoint used by the mobile app
        requires Aliyun captcha tokens and rejects AJ tokens with HTTP 500.
        """
        from .captcha import solve_captcha

        captcha_verification = await solve_captcha(
            self._session, base_url=DEFAULT_BASE_URL
        )
        if not captcha_verification:
            raise CheryEuropeAuthError("Captcha verification failed")

        body = {
            "email": email,
            "module": LOGIN_MODULE,
            "captchaVerification": captcha_verification,
        }
        from .signing import get_marketing_v2_headers

        headers = get_marketing_v2_headers(content_type=HEADER_FORM_CONTENT_TYPE)
        headers["Content-Type"] = HEADER_FORM_CONTENT_TYPE
        headers["Authorization"] = HEADER_BASIC_AUTH

        response = await self._post(
            DEFAULT_SEND_MAIL_CODE_ENDPOINT,
            data=body,
            headers=headers,
        )
        if not (response.get("ok") or response.get("key") == "operation.successful"):
            key = response.get("key")
            msg = response.get("msg")
            detail = f" (msg={msg})" if msg else ""
            raise CheryEuropeAuthError(
                f"Failed to send login code (key={key}){detail}"
            )

    async def login(self, email: str, code: str) -> AuthResponse:
        """Authenticate with email and OTP using SM4-ECB encryption.

        Fetches the ``defaultEnv`` bootstrap first (if not already cached) so
        the discovered TSP ``domain`` is available for subsequent BFF API
        calls, then encrypts the OTP with SM4-ECB/PKCS7 and POSTs an OAuth2
        email grant to ``/api/auth/oauth2/token`` with query parameters
        ``email=APP-LOGIN@...`` and ``code=<ciphertext>``. The plaintext OTP
        is never logged or stored after the request returns.
        """
        if self.env_config is None:
            await self.fetch_env_config()
        elif self.env_config.domain:
            self._base_url = self.env_config.domain.rstrip("/")

        from .crypto import SM4_LOGIN_KEY, sm4_encrypt_ecb_pkcs7

        encrypted_code = sm4_encrypt_ecb_pkcs7(code, SM4_LOGIN_KEY)
        params = self._build_login_params(email, encrypted_code)
        headers = self._build_login_identity_headers()
        headers["Content-Type"] = HEADER_CONTENT_TYPE
        headers["Authorization"] = HEADER_BASIC_AUTH

        response = await self._post(
            DEFAULT_LOGIN_ENDPOINT,
            params=params,
            json={},
            headers=headers,
        )
        auth_response = self._parse_auth_response(response)
        self.set_tokens(auth_response.access_token, auth_response.refresh_token)
        return auth_response

    async def refresh_token(self, refresh_token: str) -> AuthResponse:
        """Refresh an access token using a refresh-token grant.

        POSTs a form-urlencoded payload (``grant_type=refresh_token``,
        ``refresh_token=...``, ``scope=server``, plus ``client_id`` and
        ``client_secret`` when available) to the OAuth2 token endpoint with a
        ``Basic legendApp:legendApp`` auth header and identity/signing
        headers, parses the response, and updates the internal token state.
        Client credentials are resolved from the cached :class:`EnvConfig`
        when available, falling back to the constructor-supplied values.
        """
        client_id = self._resolve_client_id()
        client_secret = self._resolve_client_secret()

        payload: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "server",
        }
        if client_id:
            payload["client_id"] = client_id
        if client_secret:
            payload["client_secret"] = client_secret

        headers = self._build_signature_headers(
            method="POST",
            path=DEFAULT_LOGIN_ENDPOINT,
            body=payload,
            content_type=HEADER_FORM_CONTENT_TYPE,
        )
        headers["Content-Type"] = HEADER_FORM_CONTENT_TYPE
        headers["Authorization"] = HEADER_BASIC_AUTH

        response = await self._post(
            DEFAULT_LOGIN_ENDPOINT,
            data=payload,
            headers=headers,
        )
        auth_response = self._parse_auth_response(response)
        self.set_tokens(auth_response.access_token, auth_response.refresh_token)
        return auth_response

    async def logout(self, access_token: str) -> None:
        """Clear the local session token state."""
        if self.access_token == access_token:
            self.set_tokens(None, None)

    def set_tokens(
        self, access_token: str | None, refresh_token: str | None = None
    ) -> None:
        """Set tokens for API clients without logging sensitive values."""
        self.access_token = access_token
        self.refresh_token_value = refresh_token

    def _resolve_client_id(self) -> str | None:
        """Return the active OAuth2 client_id.

        Prefers the cached :class:`EnvConfig` (set by ``fetch_env_config``)
        and falls back to the constructor-supplied value.
        """
        if self.env_config and self.env_config.client_id:
            return self.env_config.client_id
        return self._client_id

    def _resolve_client_secret(self) -> str | None:
        """Return the active OAuth2 client_secret.

        Prefers the cached :class:`EnvConfig` (set by ``fetch_env_config``)
        and falls back to the constructor-supplied value.
        """
        if self.env_config and self.env_config.client_secret:
            return self.env_config.client_secret
        return self._client_secret

    def _build_login_params(self, email: str, encrypted_code: str) -> dict[str, str]:
        """Build OAuth2 email-grant query params for the token endpoint."""
        return {
            "email": f"{LOGIN_EMAIL_PREFIX}{email}",
            "code": encrypted_code,
            "needDecode": "0",
            "grant_type": "email",
            "scope": "server",
            "loginType": "email",
            "loginAction": "1",
        }

    def _build_login_identity_headers(self) -> dict[str, str]:
        """Identity headers for the email OTP token call (no request signature)."""
        from .signing import (
            HEADER_AGENT,
            HEADER_CLIENT_TOC,
            HEADER_DEPT_ID,
            HEADER_TENANT_CODE,
            HEADER_TENANT_ID,
            HEADER_VERSION,
        )

        return {
            "contentType": HEADER_CONTENT_TYPE,
            "agent": HEADER_AGENT,
            "version": HEADER_VERSION,
            "DEPT-ID": HEADER_DEPT_ID,
            "TENANT-ID": HEADER_TENANT_ID,
            "TENANT-CODE": HEADER_TENANT_CODE,
            "CLIENT-TOC": HEADER_CLIENT_TOC,
        }

    def _build_signature_headers(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        query_keys: list[str] | None = None,
        content_type: str = HEADER_CONTENT_TYPE,
    ) -> dict[str, str]:
        """Build request signature headers from the official app.

        Delegates to :mod:`signing.get_identity_headers` which reproduces the
        SHA-256 signing formula verified against real app captures.
        """
        from .signing import SIGN_SECRET, get_identity_headers

        return get_identity_headers(
            method=method,
            path=path,
            body=body if isinstance(body, Mapping) else None,
            secret=SIGN_SECRET,
            query_keys=query_keys,
            content_type=content_type,
        )

    async def _post(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        url = self._oauth_url(endpoint)
        _LOGGER.debug("Chery Europe auth request: POST %s", url)

        headers = {
            "Accept": HEADER_ACCEPT,
            "Accept-Language": HEADER_ACCEPT_LANGUAGE,
            "Accept-Encoding": HEADER_ACCEPT_ENCODING,
            "User-Agent": DEFAULT_USER_AGENT,
            **kwargs.pop("headers", {}),
        }

        try:
            async with self._session.post(
                url,
                timeout=REQUEST_TIMEOUT,
                headers=headers,
                **kwargs,
            ) as response:
                _LOGGER.debug(
                    "Chery Europe auth response: POST %s status=%s", url, response.status
                )
                if response.status == 401:
                    raise CheryEuropeAuthError("Authentication failed")
                if response.status == 429:
                    raise CheryEuropeRateLimitError("Rate limit exceeded")
                if response.status >= 400:
                    error_body = await response.text()
                    _LOGGER.debug(
                        "Chery Europe auth error body: POST %s status=%s body=%s",
                        url,
                        response.status,
                        error_body[:500],
                    )
                    raise CheryEuropeConnectionError(
                        f"Chery Europe auth returned status {response.status}"
                    )
                data = await response.json(content_type=None)
                if not isinstance(data, dict):
                    raise CheryEuropeAuthError("Unexpected authentication response")
                return data
        except asyncio.TimeoutError as exc:
            raise CheryEuropeTimeoutError("Authentication request timed out") from exc
        except aiohttp.ClientConnectionError as exc:
            raise CheryEuropeConnectionError("Unable to connect to Chery Europe") from exc
        except aiohttp.ClientError as exc:
            raise CheryEuropeConnectionError("Chery Europe HTTP error") from exc

    def _oauth_url(self, endpoint: str) -> str:
        """Build the full OAuth2 token endpoint URL on the public gateway.

        OAuth token minting always targets the public gateway
        (``eu-chery.cheryinternational.com``), never the TSP domain
        (``tspconsole-eu.cheryinternational.com``) returned by
        ``defaultEnv`` — that domain is only used for subsequent BFF API
        calls.
        """
        base = DEFAULT_BASE_URL.rstrip("/")
        return f"{base}{endpoint if endpoint.startswith('/') else f'/{endpoint}'}"

    def _parse_auth_response(self, data: dict[str, Any]) -> AuthResponse:
        payload = _token_payload(data)
        access_token = _first_string(
            payload,
            "accessToken",
            "access_token",
            "token",
            "tokenValue",
            "accessTokenValue",
        )
        if access_token is None:
            raise CheryEuropeAuthError("Invalid authentication response")

        refresh_token = _first_string(
            payload,
            "refreshToken",
            "refresh_token",
            "refreshTokenValue",
        ) or ""
        expires_in = _int_value(payload.get("expires_in") or payload.get("expiresIn"))
        token_type = _first_string(payload, "token_type", "tokenType") or "Bearer"
        return AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            token_type=token_type,
        )


def _token_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return the dict that contains token fields from common API envelopes."""
    for key in ("data", "result", "payload"):
        value = data.get(key)
        if isinstance(value, dict):
            nested = _token_payload(value)
            if _first_string(
                nested,
                "accessToken",
                "access_token",
                "token",
                "tokenValue",
                "accessTokenValue",
            ):
                return nested
    return data


def _first_string(data: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
