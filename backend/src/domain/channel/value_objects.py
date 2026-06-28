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

# URL-safe kebab-case: lower-case alphanumerics in hyphen-separated groups.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SLUG_MAX_LENGTH = 64


@dataclass(frozen=True)
class Currency:
    """An ISO 4217 alpha currency code (Iran-first: IRR for Rial)."""

    code: str

    def __post_init__(self) -> None:
        normalized = self.code.strip()
        if not _CURRENCY_RE.match(normalized):
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
