"""Value objects for the shipping context.

Value objects are immutable and self-validating: an instance cannot exist in an invalid
state, and equality is by value. Like the order context, shipping owns its own ``Money``
rather than importing a neighbour's -- a bounded context depends on narrow abstractions of
its neighbours, never on their domain types. A shipping price is a fixed-point ``Decimal``
(never a binary ``float``), non-negative (a free method priced at zero is valid), and
bounded to the stored precision.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from src.domain.shipping.exceptions import (
    InvalidDestinationError,
    InvalidMoneyError,
    InvalidShippingMethodCodeError,
    InvalidShippingZoneCodeError,
    InvalidWeightTableError,
    InvalidZonedRateError,
)

# A method/zone code is lower-case kebab-case ("standard", "express", "tehran") -- the stable
# key a channel's config and the checkout selection both reference.
_CODE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CODE_MAX_LENGTH = 32
# A province name is free text captured from the address; bound it to the same length the
# order's ShippingAddress allows so a valid captured province is always a valid destination.
_PROVINCE_MAX_LENGTH = 100
# Money precision mirrors the order/catalog stored precision (18 total digits, 4 decimal
# places) so a quoted price is always captured onto an order losslessly.
_MONEY_MAX_DIGITS = 18
_MONEY_MAX_DECIMAL_PLACES = 4
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class ShippingMethodCode:
    """The stable, lower-case identifier of a shipping method within a channel."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if len(normalized) > _CODE_MAX_LENGTH or not _CODE_RE.match(normalized):
            raise InvalidShippingMethodCodeError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ShippingZoneCode:
    """The stable, lower-case identifier of a shipping zone within a channel."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if len(normalized) > _CODE_MAX_LENGTH or not _CODE_RE.match(normalized):
            raise InvalidShippingZoneCodeError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Destination:
    """Where an order ships, used to resolve a zoned rate.

    Only ``province`` participates in zone matching in this slice; ``city`` is captured for a
    later, finer slice. Province is required (every checkout address has one) and normalised;
    ``match_key`` folds case and whitespace so a zone lookup is tolerant of casing.
    """

    province: str
    city: str = ""

    def __post_init__(self) -> None:
        province = self.province.strip()
        if not province or len(province) > _PROVINCE_MAX_LENGTH:
            raise InvalidDestinationError(f"province: {self.province!r}")
        object.__setattr__(self, "province", province)

        city = self.city.strip()
        if len(city) > _PROVINCE_MAX_LENGTH:
            raise InvalidDestinationError(f"city: {self.city!r}")
        object.__setattr__(self, "city", city)

    @property
    def match_key(self) -> str:
        """The province folded for case/whitespace-insensitive zone matching."""
        return self.province.casefold()


@dataclass(frozen=True)
class Money:
    """A shipping price in a single currency.

    Always a fixed-point ``Decimal`` -- never a binary ``float`` -- so rounding surprises
    cannot occur. Non-negative, finite, and bounded to the stored precision. ``currency``
    is a three-letter ISO 4217 code derived from the channel.
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
        # bool is an int subclass; Decimal is not -- reject anything that is not a genuine
        # Decimal so a float (or int) never silently becomes money.
        if not isinstance(amount, Decimal):
            raise InvalidMoneyError(f"amount must be a Decimal, got {type(amount).__name__}")
        if not amount.is_finite():
            raise InvalidMoneyError(f"amount not finite: {amount!r}")
        if amount < 0:
            raise InvalidMoneyError(f"amount must not be negative: {amount!r}")
        _sign, digits, exponent = amount.as_tuple()
        if isinstance(exponent, int) and -exponent > _MONEY_MAX_DECIMAL_PLACES:
            raise InvalidMoneyError(
                f"amount has more than {_MONEY_MAX_DECIMAL_PLACES} decimal places: {amount!r}"
            )
        if len(digits) > _MONEY_MAX_DIGITS:
            raise InvalidMoneyError(f"amount has more than {_MONEY_MAX_DIGITS} digits: {amount!r}")


@dataclass(frozen=True)
class ZonedRate:
    """A shipping method's rate: a default price plus optional per-zone overrides.

    ``for_zone`` returns the override for a given zone code when one exists, otherwise the
    default -- the money-selection rule, kept in the domain so it is unit-tested rather than
    buried in an adapter. Every override must settle in the same currency as the default (a
    mixed-currency table is a configuration bug and is rejected at construction).
    """

    default: Money
    by_zone: Mapping[str, Money] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for zone_code, price in self.by_zone.items():
            if price.currency != self.default.currency:
                raise InvalidZonedRateError(
                    f"zone {zone_code!r} price currency {price.currency} "
                    f"!= default {self.default.currency}"
                )

    def for_zone(self, zone_code: str | None) -> Money:
        if zone_code is not None:
            override = self.by_zone.get(zone_code)
            if override is not None:
                return override
        return self.default


@dataclass(frozen=True)
class WeightBracket:
    """One row of a weight-rate table: everything up to ``up_to_grams`` costs ``price``.

    ``up_to_grams`` is the inclusive upper bound of the bracket (an order weight at or below
    it falls in this bracket); ``None`` marks the open-ended overflow bracket that catches any
    heavier order. The bound, when present, is a positive integer.
    """

    up_to_grams: int | None
    price: Money

    def __post_init__(self) -> None:
        bound = self.up_to_grams
        if bound is not None and (
            isinstance(bound, bool) or not isinstance(bound, int) or bound <= 0
        ):
            raise InvalidWeightTableError(f"up_to_grams must be a positive int or None: {bound!r}")


@dataclass(frozen=True)
class WeightTable:
    """A weight-based rate: ordered brackets priced by an order's total weight.

    Brackets are sorted by their upper bound with the single open-ended overflow bracket
    (``up_to_grams=None``) last; ``price_for`` returns the price of the first bracket whose
    bound covers the weight (falling through to the overflow). A table must be non-empty, end
    in exactly one overflow bracket, have strictly increasing bounds, and settle every bracket
    in one currency -- a malformed table is a configuration bug rejected at construction.
    """

    brackets: tuple[WeightBracket, ...]

    def __post_init__(self) -> None:
        if not self.brackets:
            raise InvalidWeightTableError("a weight table must have at least one bracket")
        currency = self.brackets[0].price.currency
        last = len(self.brackets) - 1
        previous: int | None = None
        for index, bracket in enumerate(self.brackets):
            if bracket.price.currency != currency:
                raise InvalidWeightTableError(
                    f"bracket {index} currency {bracket.price.currency} != {currency}"
                )
            is_overflow = bracket.up_to_grams is None
            if is_overflow and index != last:
                raise InvalidWeightTableError("the overflow bracket must be last")
            if not is_overflow and index == last:
                raise InvalidWeightTableError("the last bracket must be the open-ended overflow")
            if bracket.up_to_grams is not None:
                if previous is not None and bracket.up_to_grams <= previous:
                    raise InvalidWeightTableError("bracket bounds must strictly increase")
                previous = bracket.up_to_grams

    @property
    def from_price(self) -> Money:
        """The lightest bracket's price -- the indicative 'from' price shown when browsing."""
        return self.brackets[0].price

    def price_for(self, weight_grams: int) -> Money:
        """The price of the first bracket whose bound covers ``weight_grams``."""
        for bracket in self.brackets:
            if bracket.up_to_grams is None or weight_grams <= bracket.up_to_grams:
                return bracket.price
        # Unreachable: construction guarantees a trailing overflow bracket.
        return self.brackets[-1].price  # pragma: no cover
