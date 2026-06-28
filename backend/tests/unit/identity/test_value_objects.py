"""Unit tests for the identity value objects.

The ``PhoneNumber`` value object owns the Iranian-mobile rule: many input
spellings, one canonical E.164 form. It is pure Python (no Django), so it is
testable in isolation and reusable by the user model's manager.
"""
from __future__ import annotations

import pytest

from src.domain.identity.exceptions import InvalidPhoneNumberError
from src.domain.identity.value_objects import PhoneNumber


class TestPhoneNumberNormalization:
    @pytest.mark.parametrize(
        "raw",
        [
            "09123456789",
            "+989123456789",
            "00989123456789",
            "9123456789",
            "+98 912 345 6789",
            "0912-345-6789",
            "  09123456789  ",
        ],
    )
    def test_accepts_and_canonicalizes_iranian_mobile_spellings(self, raw: str) -> None:
        assert PhoneNumber(raw).value == "+989123456789"

    def test_is_canonicalized_for_equality(self) -> None:
        # Two spellings of the same number are the same value object.
        assert PhoneNumber("09123456789") == PhoneNumber("+989123456789")

    def test_str_returns_the_canonical_form(self) -> None:
        assert str(PhoneNumber("09123456789")) == "+989123456789"


class TestPhoneNumberValidation:
    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "08123456789",      # not a mobile prefix (must start with 9)
            "0912345678",       # too short
            "091234567890",     # too long
            "+1 202 555 0173",  # non-Iranian country code
            "9123456789a",      # contains letters
            "not-a-number",
        ],
    )
    def test_rejects_malformed_or_non_iranian_numbers(self, raw: str) -> None:
        with pytest.raises(InvalidPhoneNumberError):
            PhoneNumber(raw)
