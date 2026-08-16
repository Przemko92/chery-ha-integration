"""Request signing and identity headers for the Chery Europe app API.

The Chery Europe app (``com.chery.eu.chery``) signs every BFF request with a
SHA-256 hex digest computed over a canonical string built from the signing
secret, the fixed nonce, the *url* header (request path with
``/api/<service>/`` stripped) and the millisecond timestamp.

Algorithm (reconstructed from the public Omoda/Jaecoo HA integration
``JackRonan/omoda-jaecoo-ha`` — ``omoda_auth.py`` ``sign_post`` — and verified
byte-for-byte against four real request captures in ``materials/chery.txt``):

    base = secret + nonce + url_header + str(timestamp_ms)
    if query_keys is not None:
        base += "[" + ",".join(str(body[k]) for k in query_keys) + "]"
    signature = sha256(base.encode("utf-8")).hexdigest()

* POST request bodies are **not** part of the signing string.
* GET query parameters are included as a bracketed CSV of **values** (in the
  order of the ``keys`` header, which mirrors the URL query order) appended
  after the timestamp.
* The signing secret is a constant hardcoded in the app binary
  (``cX5fR8lJ6pK2xD4uH1eK4pY6wA4xO0sK``), **not** the ``clientSecret``
  returned by the ``defaultEnv`` bootstrap endpoint.  The ``clientSecret`` is
  used for the OAuth2 token exchange; the signing secret is used for request
  authentication.  See ``learnings.md`` for the derivation trail.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Mapping

# ── Signing constants (from the decompiled app, same as Omoda/Jaecoo BFF) ─────

#: Hardcoded signing secret shared by the Chery/Omoda/Jaecoo "legend" BFF.
#: Extracted from the public JackRonan/omoda-jaecoo-ha integration
#: (``omoda_auth.py`` ``SIGN_SECRET``).  This is NOT the ``clientSecret``
#: from the ``defaultEnv`` response — that is used for OAuth2, not signing.
SIGN_SECRET = "cX5fR8lJ6pK2xD4uH1eK4pY6wA4xO0sK"

#: Fixed nonce used by the app for every BFF request signature.
SIGN_NONCE = "chery_legend_h5"

# MD5 marketing signing for v2 ``sendMailCode`` / ``sendSmsCode`` (Omoda-style).
MARKETING_SIGN_SECRET = "5c7af05e6fbf562842ef483ee96e06a0"
MARKETING_SIGN_NONCE = "chery_legend_marketing"
MARKETING_V2_SEND_MAIL_CODE_URL = "/marketing/v2/app/code/sendMailCode"
MARKETING_V2_SEND_SMS_CODE_URL = "/marketing/v2/app/code/sendSmsCode"

# ── Identity header constants (from chery.txt capture) ───────────────────────

HEADER_AGENT = "android"
HEADER_VERSION = "1.0.6"
HEADER_DEPT_ID = "48"
HEADER_TENANT_ID = "300001"
HEADER_TENANT_CODE = "300001"
HEADER_CLIENT_TOC = "Y"
HEADER_CONTENT_TYPE = "application/json; charset=UTF-8"

# ── URL header derivation ─────────────────────────────────────────────────────

# Pattern: /api/<service>/<rest...>  ->  /<rest...>
_API_PREFIX_RE = re.compile(r"^/api/[^/]+/")


def strip_api_prefix(path: str) -> str:
    """Strip the ``/api/<service>/`` prefix from a request path.

    For most services (``tsp``, ``community``, ``admin``) the full
    ``/api/<service>/`` prefix is stripped.  The ``auth`` service is
    special: only ``/api/`` is removed so the ``url`` header keeps the
    ``/auth/`` segment (e.g. ``/api/auth/oauth2/token`` ->
    ``/auth/oauth2/token``), matching the real app capture.

        Examples::

        /api/tsp/v1/app/env/defaultEnv          -> /v1/app/env/defaultEnv
        /api/community/v1/privacyPolicy/c/...   -> /v1/privacyPolicy/c/...
        /api/admin/version/freshVersion         -> /version/freshVersion
        /api/auth/oauth2/token                  -> /auth/oauth2/token
        /api/marketing/v3/app/code/sendMailCode -> marketing/v3/app/code/sendMailCode
    """
    if path.startswith("/api/auth/"):
        return path[len("/api"):]
    # Marketing keep the service segment without a leading slash, matching the
    # real app capture (``marketing/v3/app/code/sendMailCode``).
    if path.startswith("/api/marketing/"):
        return path[len("/api/"):]
    return _API_PREFIX_RE.sub("/", path, count=1)


# ── Signature ────────────────────────────────────────────────────────────────

def build_signature(
    method: str,
    url_header: str,
    body: Mapping[str, Any] | None,
    timestamp_ms: int,
    nonce: str,
    secret: str,
    query_keys: list[str] | None = None,
) -> str:
    """Compute the request signature (lowercase SHA-256 hex digest).

    Args:
        method: HTTP method (``GET`` / ``POST``).  Currently informational —
            the signing string does not include the method.
        url_header: The ``url`` header value — the request path with
            ``/api/<service>/`` stripped (see :func:`strip_api_prefix`).
        body: Request body (POST) or query params (GET).  Used **only** when
            ``query_keys`` is provided to extract the bracketed values.
        timestamp_ms: Millisecond epoch timestamp.
        nonce: The nonce value (default :data:`SIGN_NONCE`).
        secret: The signing secret (default :data:`SIGN_SECRET`).
        query_keys: Ordered list of parameter keys whose values are appended
            to the signing string as ``[v1,v2,...]``.  Used for GET query
            strings and for POSTs that sign body fields (e.g. ``sendMailCode``).
            ``None`` when no ``keys`` header is sent.

    Returns:
        Lowercase SHA-256 hex digest of the canonical signing string.
    """
    base = f"{secret}{nonce}{url_header}{timestamp_ms}"
    if query_keys and body is not None:
        vals = ",".join(str(body[k]) for k in query_keys)
        base += f"[{vals}]"
    return hashlib.sha256(base.encode("utf-8"), usedforsecurity=False).hexdigest()


# ── Identity headers ─────────────────────────────────────────────────────────

def get_identity_headers(
    method: str,
    path: str,
    body: Mapping[str, Any] | None,
    secret: str,
    query_keys: list[str] | None = None,
    *,
    nonce: str = SIGN_NONCE,
    timestamp_ms: int | None = None,
    content_type: str = HEADER_CONTENT_TYPE,
) -> dict[str, str]:
    """Build the full set of identity/signing headers for a BFF request.

    Args:
        method: HTTP method (``GET`` / ``POST``).
        path: Full request path starting with ``/api/`` (e.g.
            ``/api/tsp/v1/app/env/defaultEnv``).  The ``/api/<service>/``
            prefix is stripped to produce the ``url`` header.
        body: Request body (POST) or query params (GET).  Used for the
            bracketed values when ``query_keys`` is provided.
        secret: The signing secret.
        query_keys: Ordered parameter keys for signed GET query strings or
            POSTs that include a ``keys`` header.  ``None`` otherwise.
        nonce: Override the default nonce (``chery_legend_h5``).
        timestamp_ms: Override the auto-generated millisecond timestamp.
        content_type: Value for the ``contentType`` identity header.
            Defaults to ``application/json; charset=UTF-8``; pass
            ``application/x-www-form-urlencoded`` for OAuth2 form requests.

    Returns:
        Dict with keys: ``signature``, ``nonce``, ``url``, ``timestamp``,
        ``contentType``, ``keys`` (only when ``query_keys`` is provided),
        ``agent``, ``version``, ``DEPT-ID``, ``TENANT-ID``, ``TENANT-CODE``,
        ``CLIENT-TOC``.
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)

    url_header = strip_api_prefix(path)
    signature = build_signature(
        method=method,
        url_header=url_header,
        body=body,
        timestamp_ms=timestamp_ms,
        nonce=nonce,
        secret=secret,
        query_keys=query_keys,
    )

    headers: dict[str, str] = {
        "signature": signature,
        "nonce": nonce,
        "url": url_header,
        "timestamp": str(timestamp_ms),
        "contentType": content_type,
        "agent": HEADER_AGENT,
        "version": HEADER_VERSION,
        "DEPT-ID": HEADER_DEPT_ID,
        "TENANT-ID": HEADER_TENANT_ID,
        "TENANT-CODE": HEADER_TENANT_CODE,
        "CLIENT-TOC": HEADER_CLIENT_TOC,
    }
    if query_keys:
        headers["keys"] = ",".join(query_keys)
    return headers


def get_marketing_v2_headers(
    *,
    timestamp_ms: int | None = None,
    content_type: str = "application/x-www-form-urlencoded",
    url_header: str = MARKETING_V2_SEND_MAIL_CODE_URL,
) -> dict[str, str]:
    """Build identity headers for marketing v2 code endpoints (MD5 signing).

    The legend BFF v2 marketing endpoints (``sendMailCode``, ``sendSmsCode``)
    use the older MD5 digest shared with AJ-Captcha and Omoda, not the SHA-256
    ``chery_legend_h5`` scheme used by v3.

    ``url_header`` must match the signed path for the endpoint being called
    (mail vs SMS); the MD5 base includes this value.
    """
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)

    base = f"{MARKETING_SIGN_SECRET}{MARKETING_SIGN_NONCE}{url_header}{timestamp_ms}"
    signature = hashlib.md5(base.encode("utf-8"), usedforsecurity=False).hexdigest()

    return {
        "signature": signature,
        "nonce": MARKETING_SIGN_NONCE,
        "url": url_header,
        "timestamp": str(timestamp_ms),
        "contentType": content_type,
        "agent": HEADER_AGENT,
        "version": HEADER_VERSION,
        "DEPT-ID": HEADER_DEPT_ID,
        "TENANT-ID": HEADER_TENANT_ID,
        "TENANT-CODE": HEADER_TENANT_CODE,
        "CLIENT-TOC": HEADER_CLIENT_TOC,
    }