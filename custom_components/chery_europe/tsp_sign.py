"""Chery Vehicle SDK REST signing for tspconsole endpoints."""

from __future__ import annotations

import base64
import hashlib
from typing import Any

APP_ID = "eu-1"
APP_SECRET = "EBUJPYr7oDd48C9Te9c755942Y7T48dV293Y4Z931J098X41aYf0"


def half_secret(secret: str = APP_SECRET) -> str:
    """Return even-index characters from the SDK app secret."""
    return "".join(secret[index] for index in range(len(secret)) if index % 2 == 0)


HALF = half_secret()


def _flatten_value(value: Any) -> Any:
    if isinstance(value, list):
        parts: list[str] = []
        for element in value:
            if isinstance(element, dict):
                flattened = _flatten_obj(element)
                for key in sorted(flattened.keys()):
                    item = flattened[key]
                    if item in (None, ""):
                        continue
                    parts.append(f"{key}={item}&")
            else:
                parts.append(str(element))
        serialized = "".join(parts)
        if serialized.endswith("&"):
            serialized = serialized[:-1]
        return serialized
    return value


def _flatten_obj(obj: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (_flatten_value(value) if isinstance(value, list) else value)
        for key, value in obj.items()
    }


def build_sign(params: dict[str, Any], timestamp_ms: int, half: str = HALF) -> str:
    """Build the uppercase base64 SHA-256 signature for a tspconsole request."""
    flattened = _flatten_obj(params)
    parts: list[str] = []
    for key in sorted(flattened.keys()):
        value = flattened[key]
        if value in (None, ""):
            continue
        parts.append(f"{key}={value}&")
    base = "".join(parts) + f"secretKey={half}&timestamp={timestamp_ms}"
    digest = hashlib.sha256(base.encode("utf-8"), usedforsecurity=False).digest()
    return base64.b64encode(digest).decode().upper()


def sign_body(body_params: dict[str, Any], timestamp_ms: int) -> dict[str, Any]:
    """Return the signed JSON body for a tspconsole POST."""
    body = dict(body_params)
    body["appId"] = APP_ID
    body["sign"] = build_sign(body, timestamp_ms)
    return body


def auth_headers(user_token: str, timestamp_ms: int, tenant_id: str = "") -> dict[str, str]:
    """Return Authorization/timestamp headers for tspconsole."""
    return {
        "Authorization": user_token,
        "timestamp": str(timestamp_ms),
        "x-TenantId": tenant_id or "",
    }
