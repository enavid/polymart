"""Value objects for the identity context.

Value objects are immutable and self-validating: an instance cannot exist in an
invalid state. ``PhoneNumber`` accepts the many spellings an Iranian user might
type and stores a single canonical E.164 form, so equality and lookups are
unambiguous everywhere downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.domain.identity.exceptions import InvalidPhoneNumberError

# Iran country code and the national significant number for a mobile line: a
# leading 9 followed by nine digits (e.g. 9123456789 -> +989123456789).
_IRAN_COUNTRY_CODE = "98"
_IRAN_MOBILE_NSN_RE = re.compile(r"^9\d{9}$")
# Separators a human commonly types; stripped before parsing.
_SEPARATORS_RE = re.compile(r"[\s\-()]")


def _to_national_significant_number(raw: str) -> str:
    """Reduce any accepted spelling to the 10-digit national number, or raise."""
    cleaned = _SEPARATORS_RE.sub("", raw.strip())
    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    elif cleaned.startswith("00"):
        cleaned = cleaned[2:]

    if not cleaned.isdigit():
        raise InvalidPhoneNumberError(raw)

    if cleaned.startswith(_IRAN_COUNTRY_CODE) and len(cleaned) == 12:
        nsn = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        nsn = cleaned[1:]
    elif len(cleaned) == 10:
        nsn = cleaned
    else:
        raise InvalidPhoneNumberError(raw)

    if not _IRAN_MOBILE_NSN_RE.match(nsn):
        raise InvalidPhoneNumberError(raw)
    return nsn


@dataclass(frozen=True)
class PhoneNumber:
    """An Iranian mobile number stored in canonical E.164 form (+98...)."""

    value: str

    def __post_init__(self) -> None:
        canonical = f"+{_IRAN_COUNTRY_CODE}{_to_national_significant_number(self.value)}"
        # Bypass the frozen guard to store the normalized value.
        object.__setattr__(self, "value", canonical)

    def __str__(self) -> str:
        return self.value
