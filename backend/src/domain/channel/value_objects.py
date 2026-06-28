"""Value objects for the channel context.

Value objects are immutable and self-validating: an instance cannot exist in an
invalid state. They carry no identity -- equality is by value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.domain.channel.exceptions import InvalidChannelSlugError, InvalidCurrencyCodeError

# ISO 4217 alpha codes are exactly three upper-case ASCII letters (e.g. IRR, USD).
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

# Active ISO 4217 circulating-currency codes a storefront can price in. Funds,
# test codes (XTS/XXX), and precious metals (XAU/XAG/XPT/XPD) are intentionally
# excluded -- they are not spendable storefront currencies. Iran-first: IRR.
# Extend this set when onboarding a market that uses a currency not yet listed.
_ISO_4217_CODES = frozenset(
    {
        "AED",
        "AFN",
        "ALL",
        "AMD",
        "ANG",
        "AOA",
        "ARS",
        "AUD",
        "AWG",
        "AZN",
        "BAM",
        "BBD",
        "BDT",
        "BGN",
        "BHD",
        "BIF",
        "BMD",
        "BND",
        "BOB",
        "BRL",
        "BSD",
        "BTN",
        "BWP",
        "BYN",
        "BZD",
        "CAD",
        "CDF",
        "CHF",
        "CLP",
        "CNY",
        "COP",
        "CRC",
        "CUP",
        "CVE",
        "CZK",
        "DJF",
        "DKK",
        "DOP",
        "DZD",
        "EGP",
        "ERN",
        "ETB",
        "EUR",
        "FJD",
        "FKP",
        "GBP",
        "GEL",
        "GHS",
        "GIP",
        "GMD",
        "GNF",
        "GTQ",
        "GYD",
        "HKD",
        "HNL",
        "HTG",
        "HUF",
        "IDR",
        "ILS",
        "INR",
        "IQD",
        "IRR",
        "ISK",
        "JMD",
        "JOD",
        "JPY",
        "KES",
        "KGS",
        "KHR",
        "KMF",
        "KPW",
        "KRW",
        "KWD",
        "KYD",
        "KZT",
        "LAK",
        "LBP",
        "LKR",
        "LRD",
        "LSL",
        "LYD",
        "MAD",
        "MDL",
        "MGA",
        "MKD",
        "MMK",
        "MNT",
        "MOP",
        "MRU",
        "MUR",
        "MVR",
        "MWK",
        "MXN",
        "MYR",
        "MZN",
        "NAD",
        "NGN",
        "NIO",
        "NOK",
        "NPR",
        "NZD",
        "OMR",
        "PAB",
        "PEN",
        "PGK",
        "PHP",
        "PKR",
        "PLN",
        "PYG",
        "QAR",
        "RON",
        "RSD",
        "RUB",
        "RWF",
        "SAR",
        "SBD",
        "SCR",
        "SDG",
        "SEK",
        "SGD",
        "SHP",
        "SLE",
        "SOS",
        "SRD",
        "SSP",
        "STN",
        "SVC",
        "SYP",
        "SZL",
        "THB",
        "TJS",
        "TMT",
        "TND",
        "TOP",
        "TRY",
        "TTD",
        "TWD",
        "TZS",
        "UAH",
        "UGX",
        "USD",
        "UYU",
        "UZS",
        "VED",
        "VES",
        "VND",
        "VUV",
        "WST",
        "XAF",
        "XCD",
        "XOF",
        "XPF",
        "YER",
        "ZAR",
        "ZMW",
        "ZWL",
    }
)

# URL-safe kebab-case: lower-case alphanumerics in hyphen-separated groups.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SLUG_MAX_LENGTH = 64


@dataclass(frozen=True)
class Currency:
    """An ISO 4217 alpha currency code (Iran-first: IRR for Rial)."""

    code: str

    def __post_init__(self) -> None:
        normalized = self.code.strip()
        if not _CURRENCY_RE.match(normalized) or normalized not in _ISO_4217_CODES:
            raise InvalidCurrencyCodeError(self.code)
        # Bypass the frozen guard to store the normalized value.
        object.__setattr__(self, "code", normalized)

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class ChannelSlug:
    """A stable, URL-safe identifier for a channel."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if len(normalized) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(normalized):
            raise InvalidChannelSlugError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value
