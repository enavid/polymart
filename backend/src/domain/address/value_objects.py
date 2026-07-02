"""Value objects for the address context.

Value objects are immutable and self-validating: an instance cannot exist in an
invalid state. The address context deliberately owns its own ``PhoneNumber`` rather
than importing the identity context's -- a bounded context depends only on narrow
abstractions of its neighbours, never on their domain types (the same convention the
cart and order contexts already follow for ``Money``/``Sku``).

Addresses are scoped to Iran (the platform's first-class market, see CLAUDE.md): the
phone number is an Iranian mobile number and the postal code is the ten-digit Iranian
format. There is no country field -- adding multi-country support is a future concern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.domain.address.exceptions import (
    InvalidAddressIdError,
    InvalidAddressLineError,
    InvalidCityError,
    InvalidPhoneNumberError,
    InvalidPostalCodeError,
    InvalidProvinceError,
    InvalidRecipientNameError,
)

_RECIPIENT_NAME_MAX_LENGTH = 200
_PROVINCE_MAX_LENGTH = 100
_CITY_MAX_LENGTH = 100
_ADDRESS_LINE_MAX_LENGTH = 255
_POSTAL_CODE_RE = re.compile(r"^\d{10}$")
_SEPARATORS_RE = re.compile(r"[\s\-()]")

# An address id is an opaque, unguessable public reference (never a sequential id,
# which would let one shopper enumerate another's addresses), mirroring the order
# context's ``OrderNumber``. Upper-case alphanumeric with dashes, bounded.
_ADDRESS_ID_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
_ADDRESS_ID_MIN_LENGTH = 6
_ADDRESS_ID_MAX_LENGTH = 40

# Iran country code and the national significant number for a mobile line: a leading
# 9 followed by nine digits (e.g. 9123456789 -> +989123456789).
_IRAN_COUNTRY_CODE = "98"
_IRAN_MOBILE_NSN_RE = re.compile(r"^9\d{9}$")


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
class RecipientName:
    """The name of the person a shipment is addressed to."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized or len(normalized) > _RECIPIENT_NAME_MAX_LENGTH:
            raise InvalidRecipientNameError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PhoneNumber:
    """The recipient's Iranian mobile number, stored in canonical E.164 form."""

    value: str

    def __post_init__(self) -> None:
        canonical = f"+{_IRAN_COUNTRY_CODE}{_to_national_significant_number(self.value)}"
        object.__setattr__(self, "value", canonical)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Province:
    """The province (ostan) of the address."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized or len(normalized) > _PROVINCE_MAX_LENGTH:
            raise InvalidProvinceError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class City:
    """The city of the address."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized or len(normalized) > _CITY_MAX_LENGTH:
            raise InvalidCityError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PostalCode:
    """A ten-digit Iranian postal code (separators are stripped, not validated)."""

    value: str

    def __post_init__(self) -> None:
        normalized = _SEPARATORS_RE.sub("", self.value.strip())
        if not _POSTAL_CODE_RE.match(normalized):
            raise InvalidPostalCodeError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AddressLine:
    """One line of a street address (line 1 is required, line 2 is optional)."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized or len(normalized) > _ADDRESS_LINE_MAX_LENGTH:
            raise InvalidAddressLineError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AddressId:
    """The public, unguessable reference to a saved address.

    Deliberately not the database id: an address id appears in URLs, so a guessable
    sequential id would let one shopper enumerate another's addresses. The generator
    (a port) produces the value; this object owns only its shape.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if (
            len(normalized) < _ADDRESS_ID_MIN_LENGTH
            or len(normalized) > _ADDRESS_ID_MAX_LENGTH
            or not _ADDRESS_ID_RE.match(normalized)
        ):
            raise InvalidAddressIdError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
