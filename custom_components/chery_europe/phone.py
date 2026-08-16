"""Phone number normalization for SMS login.

Single cleanup point for national number + country calling code before they are
stored in entry data and used in ``APP-LOGIN@<phone>_<area>`` / ``sendSmsCode``.

When in doubt, do **not** strip digits: a failed SMS attempt is recoverable; a
mutilated number re-shown in the form and written to ``entry.data`` is not.
Country code is only peeled from the number when the user declared an
international form (``+`` or ``00``).
"""

from __future__ import annotations

from .const import DEFAULT_AREA_CODE

_LONG_INTERNATIONAL_PREFIX = "00"
_MAX_AREA_DIGITS = 3


def normalize_phone(
    number: str | None, area_code: str | None
) -> tuple[str, str]:
    """Return ``(national_number, area_code)`` digits only, or ``("", "")`` if unusable."""

    def _digits(value: str | None) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    written_area = str(area_code or "").strip()
    if not written_area:
        area = DEFAULT_AREA_CODE
    else:
        area = _digits(written_area).lstrip("0")
        if not 1 <= len(area) <= _MAX_AREA_DIGITS:
            return "", ""

    raw = str(number or "").strip()
    national = _digits(raw)
    international = raw.startswith("+") or national.startswith(
        _LONG_INTERNATIONAL_PREFIX
    )
    if national.startswith(_LONG_INTERNATIONAL_PREFIX):
        national = national[len(_LONG_INTERNATIONAL_PREFIX) :]
    if international and national.startswith(area):
        national = national[len(area) :]

    national = national.lstrip("0")

    if not 6 <= len(national) <= 15 - len(area):
        return "", ""
    return national, area


def mobile_login_identity(phone: str, area_code: str) -> str:
    """Build the OAuth ``mobile`` identity ``APP-LOGIN@<phone>_<area>``."""
    from .const import LOGIN_MOBILE_PREFIX

    phone = str(phone).lstrip("+").replace(" ", "")
    area = "".join(ch for ch in str(area_code or "") if ch.isdigit()).lstrip("0")
    return f"{LOGIN_MOBILE_PREFIX}{phone}_{area}"


def mask_phone(phone: str, area_code: str) -> str:
    """Mask a phone for titles/logs: ``+48 ***1234``."""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    area = "".join(ch for ch in str(area_code or "") if ch.isdigit()).lstrip("0")
    if len(digits) <= 4:
        tail = digits or "????"
    else:
        tail = digits[-4:]
    return f"+{area} ***{tail}" if area else f"***{tail}"
