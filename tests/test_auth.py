"""Known-answer regression tests for the Chery Europe request signing.

The three test vectors below are taken verbatim from a real app capture
(``materials/chery.txt``) — a Flutter/Dio log of ``com.chery.eu.chery``
hitting the EU BFF at ``eu-chery.cheryinternational.com``.  Each test
reconstructs the exact signing inputs (method, url header, body/query,
timestamp, nonce, secret) and asserts the signature matches the captured
value byte-for-byte.
"""

import importlib.util
from pathlib import Path

# Import signing.py directly by file path to avoid triggering the package
# __init__.py which imports homeassistant (not available in unit tests).
_SIGNING_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "chery_europe"
    / "signing.py"
)
_spec = importlib.util.spec_from_file_location("chery_signing", _SIGNING_PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

build_signature = _module.build_signature
get_identity_headers = _module.get_identity_headers
get_marketing_v2_headers = _module.get_marketing_v2_headers
strip_api_prefix = _module.strip_api_prefix
SIGN_NONCE = _module.SIGN_NONCE
SIGN_SECRET = _module.SIGN_SECRET

SECRET = SIGN_SECRET
NONCE = SIGN_NONCE


def test_strip_api_prefix():
    assert strip_api_prefix("/api/tsp/v1/app/env/defaultEnv") == "/v1/app/env/defaultEnv"
    assert strip_api_prefix("/api/community/v1/privacyPolicy/c/listPrivacyRecords") == "/v1/privacyPolicy/c/listPrivacyRecords"
    assert strip_api_prefix("/api/admin/version/freshVersion") == "/version/freshVersion"


def test_strip_api_prefix_auth():
    """The auth service keeps /auth/ in the url header (only /api/ stripped)."""
    assert strip_api_prefix("/api/auth/oauth2/token") == "/auth/oauth2/token"


def test_strip_api_prefix_marketing():
    """Marketing keeps the service segment without a leading slash."""
    assert (
        strip_api_prefix("/api/marketing/v3/app/code/sendMailCode")
        == "marketing/v3/app/code/sendMailCode"
    )


def test_marketing_v2_headers_sendMailCode():
    """MD5 marketing headers for v2 sendMailCode (Omoda-style, no keys bracket)."""
    headers = get_marketing_v2_headers(timestamp_ms=1786686168819)
    assert headers["nonce"] == "chery_legend_marketing"
    assert headers["url"] == "/marketing/v2/app/code/sendMailCode"
    assert headers["timestamp"] == "1786686168819"
    assert headers["contentType"] == "application/x-www-form-urlencoded"
    assert headers["agent"] == "android"
    assert "keys" not in headers


def test_marketing_v2_headers_sendSmsCode():
    """MD5 marketing headers for v2 sendSmsCode use the SMS url path."""
    headers = get_marketing_v2_headers(
        timestamp_ms=1786686168819,
        url_header="/marketing/v2/app/code/sendSmsCode",
    )
    assert headers["url"] == "/marketing/v2/app/code/sendSmsCode"
    import hashlib

    expected = hashlib.md5(
        b"5c7af05e6fbf562842ef483ee96e06a0chery_legend_marketing"
        b"/marketing/v2/app/code/sendSmsCode1786686168819",
        usedforsecurity=False,
    ).hexdigest()
    assert headers["signature"] == expected


def test_marketing_v2_headers_signature_is_md5():
    import hashlib

    headers = get_marketing_v2_headers(timestamp_ms=1000)
    expected = hashlib.md5(
        b"5c7af05e6fbf562842ef483ee96e06a0chery_legend_marketing"
        b"/marketing/v2/app/code/sendMailCode1000",
        usedforsecurity=False,
    ).hexdigest()
    assert headers["signature"] == expected


def test_signature_vector_defaultEnv():
    """GET /api/tsp/v1/app/env/defaultEnv — no body, no query."""
    sig = build_signature(
        method="GET",
        url_header="/v1/app/env/defaultEnv",
        body=None,
        timestamp_ms=1786648055328,
        nonce=NONCE,
        secret=SECRET,
        query_keys=None,
    )
    assert sig == "b281cbac80c94ddead8b39830e992c9b0573123e2097d099a8c1bf88b6fdcb9b"


def test_signature_vector_listPrivacyRecords():
    """POST /api/community/v1/privacyPolicy/c/listPrivacyRecords — body present but NOT signed."""
    body = {"appType": 0, "appVersion": "1.0.6", "deviceId": "2374d581f2f6c443"}
    sig = build_signature(
        method="POST",
        url_header="/v1/privacyPolicy/c/listPrivacyRecords",
        body=body,
        timestamp_ms=1786648055389,
        nonce=NONCE,
        secret=SECRET,
        query_keys=None,
    )
    assert sig == "b175052a9ad257458cc7e6c5ae9f9d33adf52979e764ea4797c2e9bcd71b34a2"


def test_signature_vector_freshVersion():
    """GET /api/admin/version/freshVersion — query params signed as bracketed CSV."""
    query = {"versionNumber": "1.0.6", "terminalType": "0", "platformCode": "PGY"}
    query_keys = ["versionNumber", "terminalType", "platformCode"]
    sig = build_signature(
        method="GET",
        url_header="/version/freshVersion",
        body=query,
        timestamp_ms=1786648055437,
        nonce=NONCE,
        secret=SECRET,
        query_keys=query_keys,
    )
    assert sig == "7fea58df1d9a6ba2412eef1428be64beb760f71efa42570d18376bb322a3bd0e"


def test_identity_headers_defaultEnv():
    """Full identity headers for the defaultEnv GET request."""
    headers = get_identity_headers(
        method="GET",
        path="/api/tsp/v1/app/env/defaultEnv",
        body=None,
        secret=SECRET,
        timestamp_ms=1786648055328,
    )
    assert headers["signature"] == "b281cbac80c94ddead8b39830e992c9b0573123e2097d099a8c1bf88b6fdcb9b"
    assert headers["nonce"] == "chery_legend_h5"
    assert headers["url"] == "/v1/app/env/defaultEnv"
    assert headers["timestamp"] == "1786648055328"
    assert headers["contentType"] == "application/json; charset=UTF-8"
    assert headers["agent"] == "android"
    assert headers["version"] == "1.0.6"
    assert headers["DEPT-ID"] == "48"
    assert headers["TENANT-ID"] == "300001"
    assert headers["TENANT-CODE"] == "300001"
    assert headers["CLIENT-TOC"] == "Y"
    assert "keys" not in headers


def test_identity_headers_freshVersion():
    """Full identity headers for the freshVersion GET-with-query request."""
    query = {"versionNumber": "1.0.6", "terminalType": "0", "platformCode": "PGY"}
    query_keys = ["versionNumber", "terminalType", "platformCode"]
    headers = get_identity_headers(
        method="GET",
        path="/api/admin/version/freshVersion",
        body=query,
        secret=SECRET,
        query_keys=query_keys,
        timestamp_ms=1786648055437,
    )
    assert headers["signature"] == "7fea58df1d9a6ba2412eef1428be64beb760f71efa42570d18376bb322a3bd0e"
    assert headers["url"] == "/version/freshVersion"
    assert headers["keys"] == "versionNumber,terminalType,platformCode"


def test_identity_headers_listPrivacyRecords():
    """Full identity headers for the listPrivacyRecords POST request."""
    body = {"appType": 0, "appVersion": "1.0.6", "deviceId": "2374d581f2f6c443"}
    headers = get_identity_headers(
        method="POST",
        path="/api/community/v1/privacyPolicy/c/listPrivacyRecords",
        body=body,
        secret=SECRET,
        timestamp_ms=1786648055389,
    )
    assert headers["signature"] == "b175052a9ad257458cc7e6c5ae9f9d33adf52979e764ea4797c2e9bcd71b34a2"
    assert headers["url"] == "/v1/privacyPolicy/c/listPrivacyRecords"
    assert "keys" not in headers


# ── SM4 crypto helper tests (no homeassistant dependency) ────────────────────

import base64 as _b64  # noqa: E402

from gmssl.sm4 import CryptSM4, SM4_DECRYPT  # noqa: E402

_CRYPTO_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "chery_europe"
    / "crypto.py"
)
_cspec = importlib.util.spec_from_file_location("chery_crypto", _CRYPTO_PATH)
_cmod = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(_cmod)

sm4_encrypt_ecb_pkcs7 = _cmod.sm4_encrypt_ecb_pkcs7
SM4_LOGIN_KEY = _cmod.SM4_LOGIN_KEY


def test_sm4_encrypt_returns_base64():
    ct = sm4_encrypt_ecb_pkcs7("hello", SM4_LOGIN_KEY)
    raw = _b64.b64decode(ct)
    assert len(raw) % 16 == 0


def test_sm4_encrypt_round_trips():
    plaintext = "super-secret-password"
    ct = sm4_encrypt_ecb_pkcs7(plaintext, SM4_LOGIN_KEY)
    dec = CryptSM4()
    dec.set_key(SM4_LOGIN_KEY, SM4_DECRYPT)
    assert dec.crypt_ecb(_b64.b64decode(ct)) == plaintext.encode("utf-8")


def test_sm4_encrypt_does_not_return_plaintext():
    ct = sm4_encrypt_ecb_pkcs7("super-secret-password", SM4_LOGIN_KEY)
    assert "super-secret-password" not in ct


# ── Login encryption tests (require homeassistant) ───────────────────────────

import json as _json  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import aiohttp  # noqa: E402
import pytest  # noqa: E402


def _ha():
    pytest.importorskip("homeassistant")


def _env_config(domain="https://tsp.example.com"):
    from custom_components.chery_europe.types.env_models import EnvConfig

    return EnvConfig.from_dict(
        {
            "domain": domain,
            "clientId": "appCheryLionCloud",
            "clientSecret": "D5HkR0Z1yX8cCM8MNeMw2AC9",
            "tenantId": "300001",
        }
    )


def _mock_login_post(response_status=200, response_json=None):
    response = MagicMock()
    response.status = response_status
    response.json = AsyncMock(return_value=response_json or {})
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=response)
    cm.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock(spec=aiohttp.ClientSession)
    session.post = MagicMock(return_value=cm)
    return session, response


_TOKEN_RESPONSE = {
    "data": {
        "access_token": "tok-123",
        "refresh_token": "ref-456",
        "expires_in": 7200,
        "token_type": "Bearer",
    }
}


@pytest.mark.asyncio
async def test_login_encrypts_otp_code():
    _ha()
    from custom_components.chery_europe.auth import CheryEuropeAuth

    session, _ = _mock_login_post(200, _TOKEN_RESPONSE)
    auth = CheryEuropeAuth(session)
    auth.env_config = _env_config()

    await auth.login("driver@example.com", "123456")

    session.post.assert_called_once()
    call = session.post.call_args
    url = call.args[0]
    assert url == "https://eu-chery.cheryinternational.com/api/auth/oauth2/token"

    kwargs = call.kwargs
    params = kwargs["params"]
    headers = kwargs["headers"]

    assert params["email"] == "APP-LOGIN@driver@example.com"
    assert params["needDecode"] == "0"
    assert params["grant_type"] == "email"
    assert params["scope"] == "server"
    assert params["loginType"] == "email"
    assert params["loginAction"] == "1"
    assert "username" not in params
    assert "password" not in params
    assert kwargs.get("json") == {}

    encrypted = params["code"]
    assert encrypted != "123456"
    raw = _b64.b64decode(encrypted)
    assert len(raw) % 16 == 0
    dec = CryptSM4()
    dec.set_key(SM4_LOGIN_KEY, SM4_DECRYPT)
    assert dec.crypt_ecb(raw) == b"123456"

    assert "123456" not in _json.dumps(params)

    assert "signature" not in headers
    assert "nonce" not in headers
    assert "url" not in headers
    assert "timestamp" not in headers
    assert headers["Content-Type"] == "application/json; charset=UTF-8"
    assert headers["Authorization"] == "Basic bGVnZW5kQXBwOmxlZ2VuZEFwcA=="
    assert headers["contentType"] == "application/json; charset=UTF-8"
    assert headers["Accept"] == "application/json, text/plain, */*"
    assert headers["Accept-Language"] == "pl-PL"
    assert headers["Accept-Encoding"] == "gzip, deflate"
    assert "keys" not in headers

    assert auth.access_token == "tok-123"
    assert auth.refresh_token_value == "ref-456"


@pytest.mark.asyncio
async def test_login_fetches_env_config_when_not_cached():
    _ha()
    from custom_components.chery_europe.auth import CheryEuropeAuth

    session, _ = _mock_login_post(200, _TOKEN_RESPONSE)
    auth = CheryEuropeAuth(session)
    auth.fetch_env_config = AsyncMock(return_value=_env_config())

    await auth.login("driver@example.com", "123456")

    auth.fetch_env_config.assert_awaited_once()


@pytest.mark.asyncio
async def test_login_skips_env_config_when_already_cached():
    _ha()
    from custom_components.chery_europe.auth import CheryEuropeAuth

    session, _ = _mock_login_post(200, _TOKEN_RESPONSE)
    auth = CheryEuropeAuth(session)
    auth.env_config = _env_config()
    auth.fetch_env_config = AsyncMock()

    await auth.login("driver@example.com", "123456")

    auth.fetch_env_config.assert_not_awaited()


@pytest.mark.asyncio
async def test_login_url_uses_public_gateway_not_tsp_domain():
    _ha()
    from custom_components.chery_europe.auth import CheryEuropeAuth

    session, _ = _mock_login_post(200, _TOKEN_RESPONSE)
    auth = CheryEuropeAuth(session, base_url="https://placeholder.invalid")
    auth.env_config = _env_config(domain="https://tspconsole-eu.cheryinternational.com")

    await auth.login("user@example.com", "123456")

    url = session.post.call_args.args[0]
    assert url == "https://eu-chery.cheryinternational.com/api/auth/oauth2/token"


@pytest.mark.asyncio
async def test_login_does_not_store_plaintext_code():
    _ha()
    from custom_components.chery_europe.auth import CheryEuropeAuth

    session, _ = _mock_login_post(200, _TOKEN_RESPONSE)
    auth = CheryEuropeAuth(session)
    auth.env_config = _env_config()

    await auth.login("user@example.com", "my-otp-code")

    assert not hasattr(auth, "password")
    assert not hasattr(auth, "_password")
    assert not hasattr(auth, "code")
    assert not hasattr(auth, "_code")


@pytest.mark.asyncio
async def test_send_mail_code_posts_signed_form_body():
    _ha()
    from custom_components.chery_europe.auth import CheryEuropeAuth

    session, _ = _mock_login_post(
        200, {"ok": True, "key": "operation.successful", "data": None}
    )
    auth = CheryEuropeAuth(session)

    with patch(
        "custom_components.chery_europe.captcha.solve_captcha",
        new=AsyncMock(return_value="captcha-token"),
    ):
        await auth.send_mail_code("driver@example.com")

    call = session.post.call_args
    assert call.args[0].endswith("/api/marketing/v2/app/code/sendMailCode")
    body = call.kwargs["data"]
    headers = call.kwargs["headers"]
    assert body == {
        "email": "driver@example.com",
        "module": "APP-LOGIN",
        "captchaVerification": "captcha-token",
    }
    assert headers["url"] == "/marketing/v2/app/code/sendMailCode"
    assert headers["nonce"] == "chery_legend_marketing"
    assert "signature" in headers
    assert "keys" not in headers
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert headers["Authorization"].startswith("Basic ")


@pytest.mark.asyncio
async def test_send_mail_code_raises_when_captcha_fails():
    _ha()
    from custom_components.chery_europe.auth import CheryEuropeAuth
    from custom_components.chery_europe.exceptions import CheryEuropeAuthError

    session, _ = _mock_login_post()
    auth = CheryEuropeAuth(session)

    with patch(
        "custom_components.chery_europe.captcha.solve_captcha",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(CheryEuropeAuthError, match="Captcha"):
            await auth.send_mail_code("driver@example.com")

    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_send_sms_code_posts_via_tls_client():
    _ha()
    from custom_components.chery_europe.auth import CheryEuropeAuth
    from custom_components.chery_europe.tls_client import SmsPostResult

    session, _ = _mock_login_post()
    auth = CheryEuropeAuth(session)
    result = SmsPostResult(
        200,
        '{"ok": true, "key": "operation.successful"}',
        "requests+tls",
    )

    with (
        patch(
            "custom_components.chery_europe.captcha.solve_captcha",
            new=AsyncMock(return_value="captcha-token"),
        ),
        patch(
            "custom_components.chery_europe.tls_client.post_waf",
            return_value=result,
        ) as post_waf,
    ):
        await auth.send_sms_code("500123456", "48", memory_path="/tmp/tls.txt")  # PHONE_PLACEHOLDER

    session.post.assert_not_called()
    post_waf.assert_called_once()
    url, body, headers = post_waf.call_args.args
    assert url.endswith("/api/marketing/v2/app/code/sendSmsCode")
    assert body == {
        "mobile": "500123456",  # PHONE_PLACEHOLDER
        "areaCode": "48",
        "module": "APP-LOGIN",
        "captchaVerification": "captcha-token",
    }
    assert headers["url"] == "/marketing/v2/app/code/sendSmsCode"
    assert post_waf.call_args.kwargs["memory_path"] == "/tmp/tls.txt"


@pytest.mark.asyncio
async def test_login_mobile_posts_form_body_not_query():
    _ha()
    from custom_components.chery_europe.auth import CheryEuropeAuth

    session, _ = _mock_login_post(200, _TOKEN_RESPONSE)
    auth = CheryEuropeAuth(session)
    auth.env_config = _env_config()

    await auth.login_mobile("500123456", "48", "123456")  # PHONE_PLACEHOLDER

    session.post.assert_called_once()
    kwargs = session.post.call_args.kwargs
    assert "params" not in kwargs or kwargs.get("params") is None
    data = kwargs["data"]
    assert data["mobile"] == "APP-LOGIN@500123456_48"  # PHONE_PLACEHOLDER
    assert data["grant_type"] == "mobile"
    assert data["loginType"] == "mobile"
    assert data["needDecode"] == "0"
    assert data["loginAction"] == "1"
    assert data["code"] != "123456"
    assert kwargs["headers"]["DEPT-ID"] == "48"
    assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert auth.access_token == "tok-123"


# ── refresh_token integration tests ──────────────────────────────────────────


def _mock_post(response_status=200, response_json=None):
    """Return a MagicMock session whose ``post(...)`` is an async context manager."""
    pytest.importorskip("homeassistant")
    from unittest.mock import AsyncMock, MagicMock

    import aiohttp

    response = MagicMock()
    response.status = response_status
    response.json = AsyncMock(return_value=response_json or {})

    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=response)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    session = MagicMock(spec=aiohttp.ClientSession)
    session.post = MagicMock(return_value=context_manager)
    return session, response


@pytest.mark.asyncio
async def test_refresh_token():
    """refresh_token posts the OAuth2 refresh grant and updates internal tokens."""
    pytest.importorskip("homeassistant")
    from custom_components.chery_europe.auth import CheryEuropeAuth
    from custom_components.chery_europe.const import DEFAULT_LOGIN_ENDPOINT

    response_json = {
        "data": {
            "accessToken": "new_access_token",
            "refreshToken": "new_refresh_token",
            "expiresIn": 7200,
            "tokenType": "Bearer",
        }
    }
    session, _ = _mock_login_post(200, response_json)
    auth = CheryEuropeAuth(
        session,
        client_id="appCheryLionCloud",
        client_secret="D5HkR0Z1yX8cCM8MNeMw2AC9",
    )

    result = await auth.refresh_token("old_refresh_token")

    assert result.access_token == "new_access_token"
    assert result.refresh_token == "new_refresh_token"
    assert auth.access_token == "new_access_token"
    assert auth.refresh_token_value == "new_refresh_token"

    session.post.assert_called_once()
    call = session.post.call_args
    url = call.args[0]
    assert url == "https://eu-chery.cheryinternational.com/api/auth/oauth2/token"
    assert url.endswith(DEFAULT_LOGIN_ENDPOINT)
    payload = call.kwargs.get("data", {})
    assert payload["grant_type"] == "refresh_token"
    assert payload["refresh_token"] == "old_refresh_token"
    assert payload["client_id"] == "appCheryLionCloud"
    assert payload["client_secret"] == "D5HkR0Z1yX8cCM8MNeMw2AC9"
    assert payload["scope"] == "server"
    headers = call.kwargs.get("headers", {})
    assert "signature" in headers
    assert "nonce" in headers
    assert headers["url"] == "/auth/oauth2/token"
    assert "timestamp" in headers
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert headers["Authorization"] == "Basic bGVnZW5kQXBwOmxlZ2VuZEFwcA=="
    assert headers["contentType"] == "application/x-www-form-urlencoded"
    assert headers["Accept"] == "application/json, text/plain, */*"
    assert headers["Accept-Language"] == "pl-PL"
    assert headers["Accept-Encoding"] == "gzip, deflate"
    assert "keys" not in headers


@pytest.mark.asyncio
async def test_refresh_token_prefers_env_config_credentials():
    """refresh_token uses EnvConfig client_id/secret over constructor values."""
    pytest.importorskip("homeassistant")
    from custom_components.chery_europe.auth import CheryEuropeAuth
    from custom_components.chery_europe.types.env_models import EnvConfig

    response_json = {
        "data": {
            "accessToken": "env_access",
            "refreshToken": "env_refresh",
            "expiresIn": 3600,
            "tokenType": "Bearer",
        }
    }
    session, _ = _mock_login_post(200, response_json)
    auth = CheryEuropeAuth(
        session,
        client_id="fallback_id",
        client_secret="fallback_secret",
    )
    auth.env_config = EnvConfig.from_dict({
        "data": {
            "clientId": "env_client_id",
            "clientSecret": "env_client_secret",
            "domain": "https://tspconsole-eu.cheryinternational.com",
        }
    })

    await auth.refresh_token("rt")

    payload = session.post.call_args.kwargs["data"]
    assert payload["client_id"] == "env_client_id"
    assert payload["client_secret"] == "env_client_secret"


@pytest.mark.asyncio
async def test_refresh_token_without_client_secret_omits_field():
    """refresh_token omits client_secret when not available."""
    pytest.importorskip("homeassistant")
    from custom_components.chery_europe.auth import CheryEuropeAuth

    response_json = {
        "data": {
            "accessToken": "a",
            "refreshToken": "r",
            "expiresIn": 0,
            "tokenType": "Bearer",
        }
    }
    session, _ = _mock_login_post(200, response_json)
    auth = CheryEuropeAuth(session)

    await auth.refresh_token("rt")

    payload = session.post.call_args.kwargs["data"]
    assert "client_secret" not in payload
    assert "client_id" not in payload
    assert payload["scope"] == "server"


def test_needs_proactive_refresh_respects_quota():
    """Access tokens near expiry should request a proactive refresh."""
    pytest.importorskip("homeassistant")
    import time

    from custom_components.chery_europe.auth import CheryEuropeAuth

    auth = CheryEuropeAuth(MagicMock())
    auth.expires_in = 1000
    auth.token_obtained_at = time.time() - 900  # 90% of lifetime elapsed
    assert auth.needs_proactive_refresh(0.8) is True

    auth.token_obtained_at = time.time() - 100  # 10% elapsed
    assert auth.needs_proactive_refresh(0.8) is False

    auth.token_obtained_at = None
    assert auth.needs_proactive_refresh(0.8) is False


def test_apply_auth_response_sets_expiry_metadata():
    pytest.importorskip("homeassistant")
    import time

    from custom_components.chery_europe.auth import CheryEuropeAuth
    from custom_components.chery_europe.types.auth_models import AuthResponse

    auth = CheryEuropeAuth(MagicMock())
    before = time.time()
    auth.apply_auth_response(
        AuthResponse(
            access_token="a",
            refresh_token="r",
            expires_in=43200,
            token_type="Bearer",
        )
    )
    after = time.time()
    assert auth.access_token == "a"
    assert auth.refresh_token_value == "r"
    assert auth.expires_in == 43200
    assert before <= (auth.token_obtained_at or 0) <= after
