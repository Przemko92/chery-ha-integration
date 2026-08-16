"""Tests for SMS phone normalization (synthetic numbers only)."""

from __future__ import annotations

import pytest

from custom_components.chery_europe.const import DEFAULT_AREA_CODE
from custom_components.chery_europe.phone import (
    mask_phone,
    mobile_login_identity,
    normalize_phone,
)

# (typed number, typed area, expected number, expected area, why)
# PHONE_PLACEHOLDER marks lines for secret scanners.
_CASES = [
    ("500123456", "48", "500123456", "48",  # PHONE_PLACEHOLDER
     "national number as labeled"),
    ("500 123.45-6", "48", "500123456", "48",  # PHONE_PLACEHOLDER
     "separators stripped"),
    ("+48 500 123456", "48", "500123456", "48",  # PHONE_PLACEHOLDER
     "international with + peels country code"),
    ("0048 500 123456", "48", "500123456", "48",  # PHONE_PLACEHOLDER
     "international 00 form"),
    ("500123456", "+48", "500123456", "48",  # PHONE_PLACEHOLDER
     "area with +"),
    ("500123456", "", "500123456", DEFAULT_AREA_CODE,  # PHONE_PLACEHOLDER
     "empty area uses default"),
    ("500123456", "+", "", "",  # PHONE_PLACEHOLDER
     "unreadable written area rejected"),
    ("12", "48", "", "", "too short"),  # PHONE_PLACEHOLDER
    ("", "48", "", "", "empty"),
]


@pytest.mark.parametrize(
    "number,area,expected_number,expected_area,_why",
    [pytest.param(*case, id=case[4][:40]) for case in _CASES],
)
def test_normalize_phone(number, area, expected_number, expected_area, _why):
    assert normalize_phone(number, area) == (expected_number, expected_area)


def test_mobile_login_identity():
    assert mobile_login_identity("500123456", "48") == "APP-LOGIN@500123456_48"  # PHONE_PLACEHOLDER


def test_mask_phone():
    assert mask_phone("500123456", "48") == "+48 ***3456"  # PHONE_PLACEHOLDER
