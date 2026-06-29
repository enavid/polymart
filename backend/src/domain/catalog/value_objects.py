"""Value objects for the catalog context.

Value objects are immutable and self-validating: an instance cannot exist in an
invalid state. They carry no identity -- equality is by value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from src.domain.catalog.enums import RuleOperator
from src.domain.catalog.exceptions import (
    InvalidAttributeChoiceError,
    InvalidAttributeCodeError,
    InvalidCategorySlugError,
    InvalidChannelReferenceError,
    InvalidCollectionSlugError,
    InvalidMediaAssetError,
    InvalidMoneyError,
    InvalidProductCodeError,
    InvalidProductTypeCodeError,
    InvalidRuleConditionError,
    InvalidSkuError,
    InvalidStockQuantityError,
)

# URL-safe kebab-case: lower-case alphanumerics in hyphen-separated groups. Codes
# are stable machine keys (e.g. "roast-level"), so the format is intentionally
# strict and shared by attribute codes and choice values.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# SKUs follow the same shape but are upper-cased: a stock-keeping unit is conventionally
# written in upper case, and a single canonical form keeps one physical item from being
# split across "abc-1" and "ABC-1".
_SKU_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
_SLUG_MAX_LENGTH = 64
_LABEL_MAX_LENGTH = 255
_URL_MAX_LENGTH = 2048
# A rule condition compares against a product's stored attribute value (text,
# number, boolean literal, or choice slug); the bound matches the product metadata
# value limit so any storable value is expressible.
_RULE_VALUE_MAX_LENGTH = 1024
# A media URL is either absolute (a CDN/object-store link) or site-relative (a
# path served by the platform), so themes can point at either without code changes.
_URL_PREFIXES = ("http://", "https://", "/")
# Money bounds. A base price is stored as a fixed-point Decimal: at most 18 total
# significant digits (matching the DB column) and 4 decimal places -- enough for
# every circulating ISO 4217 currency (including the three-decimal dinars) with a
# margin. Currency-exact rounding to each currency's own exponent is a follow-up.
_MONEY_MAX_DIGITS = 18
_MONEY_MAX_DECIMAL_PLACES = 4
# A currency is an ISO 4217 alpha code (three upper-case letters). Full membership
# (IRR/USD/...) is validated by the channel context; a price always derives its
# currency from a persisted channel, so here we only enforce the structural shape.
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
# A stock quantity is a non-negative integer bounded to the stored column's range
# (a 32-bit positive integer), so an absurd value is rejected at the domain edge
# rather than at the database.
_STOCK_MAX_QUANTITY = 2_147_483_647


@dataclass(frozen=True)
class AttributeCode:
    """A stable, URL-safe identifier for a dynamic attribute."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if len(normalized) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(normalized):
            raise InvalidAttributeCodeError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProductTypeCode:
    """A stable, URL-safe identifier for a product type."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if len(normalized) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(normalized):
            raise InvalidProductTypeCodeError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ProductCode:
    """A stable, URL-safe identifier for a product."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if len(normalized) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(normalized):
            raise InvalidProductCodeError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CategorySlug:
    """A stable, URL-safe identifier for a category (its place in the tree)."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if len(normalized) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(normalized):
            raise InvalidCategorySlugError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CollectionSlug:
    """A stable, URL-safe identifier for a collection (a curated grouping)."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if len(normalized) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(normalized):
            raise InvalidCollectionSlugError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Sku:
    """A stock-keeping unit: the unique, stable identifier of a sellable variant.

    Canonicalized to upper case so the same physical item is never recorded under
    two casings.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if len(normalized) > _SLUG_MAX_LENGTH or not _SKU_RE.match(normalized):
            raise InvalidSkuError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AttributeValue:
    """A product's value for one attribute, keyed by the attribute's code.

    The ``value`` is the canonical string form (a number, a boolean literal, a
    choice slug, or free text). Whether it conforms to the attribute's input type
    is decided by the conformance domain service, which has the definition; the
    value object only pairs a code with its stored string.
    """

    attribute: AttributeCode
    value: str


@dataclass(frozen=True)
class MediaAsset:
    """One image attached to a variant: a URL plus optional alt text.

    The URL may be absolute (``https://...``) or site-relative (``/media/...``);
    alt text is optional but bounded. This is a reference, not a stored file --
    upload/storage is an infrastructure concern handled outside the domain.
    """

    url: str
    alt_text: str = ""

    def __post_init__(self) -> None:
        url = self.url.strip()
        if (
            not url
            or len(url) > _URL_MAX_LENGTH
            or any(ch.isspace() for ch in url)
            or not url.startswith(_URL_PREFIXES)
        ):
            raise InvalidMediaAssetError(f"url {self.url!r}")
        alt_text = self.alt_text.strip()
        if len(alt_text) > _LABEL_MAX_LENGTH:
            raise InvalidMediaAssetError(f"alt_text {self.alt_text!r}")
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "alt_text", alt_text)


@dataclass(frozen=True)
class RuleCondition:
    """One predicate of a rule-based collection's membership rule.

    Pairs an attribute (by code) with an operator and the value to compare against.
    A rule selects products that satisfy a conjunction (AND) of such conditions.
    Whether the referenced attribute exists is an application-layer concern; this
    value object owns only the structural rule that the comparison value is a
    non-blank, bounded string.
    """

    attribute: AttributeCode
    operator: RuleOperator
    value: str

    def __post_init__(self) -> None:
        value = self.value.strip()
        if not value or len(value) > _RULE_VALUE_MAX_LENGTH:
            raise InvalidRuleConditionError(f"value {self.value!r}")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class AttributeChoice:
    """One allowed option of a choice-type attribute.

    ``value`` is a stable slug (the machine key persisted with each product),
    while ``label`` is the human-facing display text.
    """

    value: str
    label: str

    def __post_init__(self) -> None:
        value = self.value.strip()
        if len(value) > _SLUG_MAX_LENGTH or not _SLUG_RE.match(value):
            raise InvalidAttributeChoiceError(f"value {self.value!r}")
        label = self.label.strip()
        if not label or len(label) > _LABEL_MAX_LENGTH:
            raise InvalidAttributeChoiceError(f"label {self.label!r}")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "label", label)


@dataclass(frozen=True)
class Money:
    """A monetary amount in a single currency.

    Money is always a fixed-point ``Decimal`` -- never a binary ``float`` -- so the
    rounding surprises that make floats unfit for money cannot occur. A base price
    is strictly positive (zero/free is a promotion concern, not a base price), finite,
    and bounded to the stored precision. ``currency`` is a three-letter ISO 4217 code;
    a price always derives it from a persisted channel, so equality across currencies
    is never silently assumed.
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        self._validate_amount(self.amount)
        currency = self.currency.strip().upper()
        if not _CURRENCY_RE.match(currency):
            raise InvalidMoneyError(f"currency {self.currency!r}")
        object.__setattr__(self, "currency", currency)

    @staticmethod
    def _validate_amount(amount: Decimal) -> None:
        # bool is an int subclass; Decimal is not -- reject anything that is not a
        # genuine Decimal so a float (or int) never silently becomes a price.
        if not isinstance(amount, Decimal):
            raise InvalidMoneyError(f"amount must be a Decimal, got {type(amount).__name__}")
        if not amount.is_finite():
            raise InvalidMoneyError(f"amount not finite: {amount!r}")
        if amount <= 0:
            raise InvalidMoneyError(f"amount must be positive: {amount!r}")
        _sign, digits, exponent = amount.as_tuple()
        # ``exponent`` is the (negated) number of decimal places for a fractional
        # value; it is non-negative for a whole number, which never over-scales.
        if isinstance(exponent, int) and -exponent > _MONEY_MAX_DECIMAL_PLACES:
            raise InvalidMoneyError(
                f"amount has more than {_MONEY_MAX_DECIMAL_PLACES} decimal places: {amount!r}"
            )
        if len(digits) > _MONEY_MAX_DIGITS:
            raise InvalidMoneyError(f"amount has more than {_MONEY_MAX_DIGITS} digits: {amount!r}")


@dataclass(frozen=True)
class ChannelPrice:
    """A variant's base price in one channel: a channel reference paired with money.

    The channel is referenced by its slug (the channel lives in another bounded
    context); whether it exists, and which currency it uses, are application-layer
    concerns resolved against the channel. This value object owns only the structural
    rule that the channel reference is a non-blank, bounded string.
    """

    channel: str
    money: Money

    def __post_init__(self) -> None:
        channel = self.channel.strip()
        if not channel or len(channel) > _SLUG_MAX_LENGTH:
            raise InvalidChannelReferenceError(self.channel)
        object.__setattr__(self, "channel", channel)


@dataclass(frozen=True)
class StockQuantity:
    """The number of sellable units of a variant on hand.

    A quantity is a non-negative integer: zero is a valid (out-of-stock) state, but
    a negative count is never representable. ``bool`` is an ``int`` subclass, so it
    is rejected explicitly -- ``True`` must never silently become a quantity of one.
    The upper bound matches the stored column so an out-of-range value fails here
    rather than at the database. Reservation/deduction on order is a later phase;
    this is only the on-hand count.
    """

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise InvalidStockQuantityError(self.value)
        if self.value < 0 or self.value > _STOCK_MAX_QUANTITY:
            raise InvalidStockQuantityError(self.value)
