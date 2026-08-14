"""AJ-Captcha blockPuzzle solver for the Chery Europe legend BFF.

Ported from the Omoda/Jaecoo HA integration (``captcha_solver.py``). The
Chery Europe mobile app uses Aliyun captcha for the v3 ``sendMailCode``
endpoint; this integration uses the shared AJ-Captcha flow (v2 endpoint):

  POST /api/code/create  -> puzzle images + secretKey + token
  POST /api/code/check   -> verify slide (encrypted pointJson in query)

``captchaVerification`` is AES-ECB/PKCS7 of ``token---{"x":gapX,"y":5}`` and
is passed to ``marketing/v2/app/code/sendMailCode``.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import time
from typing import Any

import aiohttp

from .const import (
    DEFAULT_BASE_URL,
    HEADER_BASIC_AUTH,
    HEADER_TENANT_CODE,
    HEADER_TENANT_ID,
)

_LOGGER = logging.getLogger(__name__)

CAPTCHA_SECRET = "5c7af05e6fbf562842ef483ee96e06a0"
CAPTCHA_NONCE = "chery_legend_marketing"
CAPTCHA_CREATE_PATH = "/code/create"
CAPTCHA_CHECK_PATH = "/code/check"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


def _md5(value: str) -> str:
    return hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()


def _aes_b64(plaintext: str, key: str) -> str:
    """AES-ECB/PKCS7 encrypt and return base64 ciphertext."""
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key_bytes = key.encode("utf-8")
    data = plaintext.encode("utf-8")
    pad_len = 16 - (len(data) % 16)
    padded = data + bytes([pad_len] * pad_len)
    cipher = Cipher(algorithms.AES(key_bytes), modes.ECB(), default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode()


def _signed_headers(path: str) -> dict[str, str]:
    ts = int(time.time() * 1000)
    return {
        "Authorization": HEADER_BASIC_AUTH,
        "tenant": HEADER_TENANT_CODE,
        "TENANT-ID": HEADER_TENANT_ID,
        "TENANT-CODE": HEADER_TENANT_CODE,
        "User-Agent": "okhttp/4.9.0",
        "nonce": CAPTCHA_NONCE,
        "timestamp": str(ts),
        "url": path,
        "signature": _md5(f"{CAPTCHA_SECRET}{CAPTCHA_NONCE}{path}{ts}"),
        "Content-Type": "application/json",
    }


def _signed_headers_query(path: str, keys_csv: str, vals_csv: str) -> dict[str, str]:
    ts = int(time.time() * 1000)
    return {
        "Authorization": HEADER_BASIC_AUTH,
        "tenant": HEADER_TENANT_CODE,
        "TENANT-ID": HEADER_TENANT_ID,
        "TENANT-CODE": HEADER_TENANT_CODE,
        "User-Agent": "okhttp/4.9.0",
        "nonce": CAPTCHA_NONCE,
        "timestamp": str(ts),
        "url": path,
        "keys": keys_csv,
        "signature": _md5(
            f"{CAPTCHA_SECRET}{CAPTCHA_NONCE}{path}{ts}[{vals_csv}]"
        ),
        "Content-Type": "application/json",
    }


def _dilate3(arr: Any) -> Any:
    import numpy as np

    padded = np.pad(arr, 1, mode="edge")
    return np.maximum.reduce(
        [
            padded[0:-2, 0:-2],
            padded[0:-2, 1:-1],
            padded[0:-2, 2:],
            padded[1:-1, 0:-2],
            padded[1:-1, 1:-1],
            padded[1:-1, 2:],
            padded[2:, 0:-2],
            padded[2:, 1:-1],
            padded[2:, 2:],
        ]
    )


def _erode3(arr: Any) -> Any:
    import numpy as np

    padded = np.pad(arr, 1, mode="edge")
    return np.minimum.reduce(
        [
            padded[0:-2, 0:-2],
            padded[0:-2, 1:-1],
            padded[0:-2, 2:],
            padded[1:-1, 0:-2],
            padded[1:-1, 1:-1],
            padded[1:-1, 2:],
            padded[2:, 0:-2],
            padded[2:, 1:-1],
            padded[2:, 2:],
        ]
    )


def find_gap_x(orig_b64: str, jigsaw_b64: str) -> int:
    """Return slide gap x via numpy shape-matching (no OpenCV)."""
    import numpy as np
    from PIL import Image

    original = np.asarray(
        Image.open(io.BytesIO(base64.b64decode(orig_b64))).convert("RGB")
    )
    jigsaw = np.asarray(
        Image.open(io.BytesIO(base64.b64decode(jigsaw_b64))).convert("RGBA")
    )
    mask = (jigsaw[:, :, 3] > 128).astype(np.uint8)
    ys, xs = np.where(mask)
    if ys.size == 0:
        return 0
    x0, y0 = int(xs.min()), int(ys.min())
    width = int(xs.max()) - x0 + 1
    height = int(ys.max()) - y0 + 1
    silhouette = mask[y0 : y0 + height, x0 : x0 + width] * 255
    outline = np.clip(
        _dilate3(silhouette.astype(np.int16)) - _erode3(silhouette.astype(np.int16)),
        0,
        255,
    ).astype(np.float64)
    white = (
        (original[:, :, 0] > 185)
        & (original[:, :, 1] > 185)
        & (original[:, :, 2] > 185)
    ).astype(np.float64)
    img_h, img_w = white.shape
    template = outline
    template_sq = float((template * template).sum())
    if template_sq <= 0 or img_h < height or img_w < width:
        return 0
    windows = np.lib.stride_tricks.sliding_window_view(white, (height, width))
    best_score, best_x = -1.0, width
    for gy in range(windows.shape[0]):
        row = windows[gy]
        numerator = np.einsum("kij,ij->k", row, template)
        denominator = np.sqrt(np.einsum("kij,kij->k", row, row) * template_sq)
        denominator[denominator == 0] = 1e-9
        scores = numerator / denominator
        scores[: max(1, width)] = 0
        gx = int(np.argmax(scores))
        if scores[gx] > best_score:
            best_score, best_x = float(scores[gx]), gx
    return int(best_x) - x0


async def _create_puzzle(
    session: aiohttp.ClientSession, api_root: str
) -> dict[str, Any] | None:
    url = f"{api_root}{CAPTCHA_CREATE_PATH}"
    try:
        async with session.post(
            url,
            json={"captchaType": "blockPuzzle"},
            headers=_signed_headers(CAPTCHA_CREATE_PATH),
            timeout=REQUEST_TIMEOUT,
        ) as response:
            data = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        _LOGGER.debug("Captcha create failed: %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    rep = (data.get("data") or {}).get("repData")
    return rep if isinstance(rep, dict) else None


async def _check_puzzle(
    session: aiohttp.ClientSession,
    api_root: str,
    token: str,
    point: dict[str, int],
    secret: str,
) -> dict[str, Any]:
    point_json = json.dumps(point, separators=(",", ":"))
    encrypted = _aes_b64(point_json, secret)
    params = {
        "captchaType": "blockPuzzle",
        "pointJson": encrypted,
        "token": token,
    }
    keys = "captchaType,pointJson,token"
    vals = f"blockPuzzle,{encrypted},{token}"
    url = f"{api_root}{CAPTCHA_CHECK_PATH}"
    try:
        async with session.post(
            url,
            params=params,
            headers=_signed_headers_query(CAPTCHA_CHECK_PATH, keys, vals),
            timeout=REQUEST_TIMEOUT,
        ) as response:
            data = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
        _LOGGER.debug("Captcha check failed: %s", exc)
        return {}
    return data if isinstance(data, dict) else {}


async def solve_captcha(
    session: aiohttp.ClientSession,
    *,
    base_url: str = DEFAULT_BASE_URL,
    max_attempts: int = 12,
) -> str | None:
    """Solve the AJ blockPuzzle and return ``captchaVerification``, or None."""
    api_root = f"{base_url.rstrip('/')}/api"
    loop = asyncio.get_running_loop()

    for attempt in range(1, max_attempts + 1):
        rep = await _create_puzzle(session, api_root)
        if not isinstance(rep, dict) or not all(
            rep.get(key)
            for key in (
                "token",
                "secretKey",
                "originalImageBase64",
                "jigsawImageBase64",
            )
        ):
            _LOGGER.debug("Captcha create invalid on attempt %s", attempt)
            await asyncio.sleep(0.3)
            continue

        token = rep["token"]
        secret = rep["secretKey"]
        gap_x = await loop.run_in_executor(
            None,
            find_gap_x,
            rep["originalImageBase64"],
            rep["jigsawImageBase64"],
        )
        point = {"x": gap_x, "y": 5}
        result = await _check_puzzle(session, api_root, token, point, secret)
        data = result.get("data") or {}
        if data.get("repCode") == "0000":
            point_json = json.dumps(point, separators=(",", ":"))
            verification = _aes_b64(f"{token}---{point_json}", secret)
            _LOGGER.debug("Captcha solved on attempt %s (x=%s)", attempt, gap_x)
            return verification

        _LOGGER.debug(
            "Captcha attempt %s rejected: x=%s code=%s",
            attempt,
            gap_x,
            data.get("repCode"),
        )
        await asyncio.sleep(0.3)

    return None
