"""HTTP client for the Aliyun-WAF-gated ``sendSmsCode`` endpoint.

Only ``sendSmsCode`` filters on TLS fingerprint. Captcha, ``sendMailCode``,
OAuth token, and TSP calls stay on aiohttp. This module posts with a short
ladder of clients that present a different ClientHello (cipher list), matching
the approach proven in the Omoda/Jaecoo HA integration.

``curl_cffi`` is optional and only used when already installed — it must not be
a manifest requirement (native wheel; install failure would block email-only
users from loading the integration).
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Callable

_LOGGER = logging.getLogger(__name__)

_MIN_TIMEOUT = 6.0

# BoringSSL-style cipher order — changes the TLS fingerprint vs stock Python.
_CIPHERS = (
    "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:"
    "ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:AES128-GCM-SHA256:"
    "AES256-GCM-SHA384:AES128-SHA:AES256-SHA:DES-CBC3-SHA"
)

# HTTP statuses that mean "slow down", not "wrong fingerprint".
_WAIT_STATUSES = (405, 429, 503)


class SmsPostResult:
    """Outcome of a POST to the WAF-gated SMS endpoint."""

    def __init__(
        self,
        status: int,
        text: str,
        client: str,
        *,
        ip_blocked: bool = False,
        network_error: bool = False,
    ) -> None:
        self.status = status
        self.text = text or ""
        self.client = client
        self.ip_blocked = ip_blocked
        self.network_error = network_error

    @property
    def passed(self) -> bool:
        """True when the WAF let the request through (JSON body from the app server)."""
        return self.text.strip().startswith("{")

    def json(self) -> dict:
        import json

        try:
            return json.loads(self.text)
        except Exception:  # noqa: BLE001
            return {}


def _is_ip_ban(status: int, text: str) -> bool:
    return status in _WAIT_STATUSES and not (text or "").strip().startswith("{")


def _tls_context():
    try:
        from urllib3.util.ssl_ import create_urllib3_context

        return create_urllib3_context(ciphers=_CIPHERS)
    except Exception:  # noqa: BLE001
        import ssl

        ctx = ssl.create_default_context()
        ctx.set_ciphers(_CIPHERS)
        return ctx


def _post_requests_tls(url: str, data: dict, headers: dict, timeout: float):
    import requests
    from requests.adapters import HTTPAdapter

    class _Adapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            kwargs["ssl_context"] = _tls_context()
            return super().init_poolmanager(*args, **kwargs)

    session = requests.Session()
    session.mount("https://", _Adapter())
    try:
        response = session.post(url, data=data, headers=headers, timeout=timeout)
        return response.status_code, response.text
    finally:
        session.close()


def _post_curl(url: str, data: dict, headers: dict, timeout: float):
    def _quote(value: str) -> str:
        return (
            '"'
            + (
                str(value)
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")
            )
            + '"'
        )

    def _header_line(key: str, value: str) -> str:
        cleaned = "".join(ch for ch in str(value) if ch not in "\r\n")
        return f"header = {_quote(f'{key}: {cleaned}')}"

    lines = [
        "silent",
        "show-error",
        "request = POST",
        f"url = {_quote(url)}",
        f"max-time = {int(timeout)}",
        'write-out = "\\n<<<STATUS:%{http_code}"',
    ]
    lines += [_header_line(k, v) for k, v in headers.items()]
    lines += [f"data-urlencode = {_quote(f'{k}={v}')}" for k, v in data.items()]

    proc = subprocess.run(
        ["curl", "-q", "--config", "-"],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout + 10,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"curl rc={proc.returncode}: {(proc.stderr or '').strip()[:120]}"
        )
    out = proc.stdout or ""
    body, sep, code = out.rpartition("\n<<<STATUS:")
    if not sep:
        raise RuntimeError(
            f"curl missing status (rc={proc.returncode}): {(proc.stderr or '')[:120]}"
        )
    return int(code.strip()), body


def _post_curl_cffi(url: str, data: dict, headers: dict, timeout: float):
    from curl_cffi import requests as cffi_requests

    response = cffi_requests.post(url, data=data, headers=headers, timeout=timeout)
    return response.status_code, response.text


def _post_requests_plain(url: str, data: dict, headers: dict, timeout: float):
    import requests

    response = requests.post(url, data=data, headers=headers, timeout=timeout)
    return response.status_code, response.text


_CLIENTS: dict[str, Callable] = {
    "requests+tls": _post_requests_tls,
    "curl": _post_curl,
    "curl_cffi": _post_curl_cffi,
    "requests": _post_requests_plain,
}
_LADDER = ["requests+tls", "curl", "curl_cffi", "requests"]


def _read_memory(path: str | None) -> str | None:
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            name = handle.read().strip()
        return name if name in _CLIENTS else None
    except Exception:  # noqa: BLE001
        return None


def _write_memory(path: str | None, name: str) -> None:
    if not path:
        return
    try:
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(name)
    except OSError:
        pass


def _client_order(memory_path: str | None) -> list[str]:
    forced = os.environ.get("CHERY_TLS_CLIENT", "").strip()
    if forced in _CLIENTS:
        return [forced]
    order = list(_LADDER)
    remembered = _read_memory(memory_path)
    if remembered:
        order.remove(remembered)
        order.insert(0, remembered)
    return order


def post_waf(
    url: str,
    data: dict,
    headers: dict,
    *,
    timeout: float = 20,
    memory_path: str | None = None,
    log: Callable[[str], None] | None = None,
) -> SmsPostResult:
    """POST through the WAF client ladder; always returns an :class:`SmsPostResult`."""
    emit = log or (lambda message: _LOGGER.debug("%s", message))
    last = SmsPostResult(0, "", "none")
    responses = 0
    order = _client_order(memory_path)
    deadline = time.monotonic() + timeout

    for index, name in enumerate(order):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            emit(f"[TLS] time budget exhausted: {len(order) - index} clients skipped")
            break
        quota = max(min(_MIN_TIMEOUT, remaining), remaining / (len(order) - index))
        try:
            status, text = _CLIENTS[name](url, data, headers, quota)
        except ImportError:
            emit(f"[TLS] {name}: not installed, skip")
            continue
        except FileNotFoundError:
            emit(f"[TLS] {name}: executable missing, skip")
            continue
        except Exception as exc:  # noqa: BLE001
            emit(f"[TLS] {name}: {type(exc).__name__}: {str(exc)[:90]}")
            continue

        responses += 1
        result = SmsPostResult(
            status, text, name, ip_blocked=_is_ip_ban(status, text)
        )
        if result.passed:
            emit(f"[TLS] {name}: WAF passed (HTTP {status})")
            _write_memory(memory_path, name)
            return result
        if result.ip_blocked:
            emit(f"[TLS] {name}: HTTP {status} — rate-limited, stopping ladder")
            return result
        emit(f"[TLS] {name}: WAF rejected (HTTP {status})")
        last = result

    if not responses:
        return SmsPostResult(0, "", last.client, network_error=True)
    return last


def curl_cffi_available() -> bool:
    """Return True when the optional curl_cffi fallback is importable."""
    try:
        import curl_cffi  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False
