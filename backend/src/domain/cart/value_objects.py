"""Value objects for the cart context.

Value objects are immutable and self-validating: an instance cannot exist in an
invalid state. They carry no identity -- equality is by value.

The cart deliberately owns its own ``Money`` and ``Sku`` rather than importing the
catalog's: a bounded context depends only on abstractions of its neighbours (a
narrow reader port), never on their domain types. The one meaningful difference is
that a catalog base price is *strictly positive* while a cart amount (a line total
or a whole-cart total) is *non-negative* -- an empty cart totals zero.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from src.domain.cart.exceptions import (
    InvalidCartQuantityError,
    InvalidChannelReferenceError,
    InvalidMoneyError,
    InvalidSkuError,
)

# A SKU is upper-cased kebab-case: the same shape the catalog canonicalises to, so a
# reference never fails to match purely on casing. The cart is not the authority on
# whether the SKU exists (the catalog is), only on its structural shape.
_SKU_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
_SKU_MAX_LENGTH = 64
_CHANNEL_MAX_LENGTH = 64
# A line quantity is a positive integer bounded so an absurd value fails at the
# domain edge rather than at the database. Zero is not a quantity -- removing a line
# is an explicit operation, never "set to zero".
_MIN_QUANTITY = 1
_MAX_QUANTITY = 1_000_000
# Money bounds mirror the catalog's stored precision (18 total digits, 4 decimal
# places) so a computed total can always be represented and persisted losslessly.
_MONEY_MAX_DIGITS = 18
_MONEY_MAX_DECIMAL_PLACES = 4
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class Sku:
    """A reference to a sellable catalog variant, canonicalised to upper case."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if len(normalized) > _SKU_MAX_LENGTH or not _SKU_RE.match(normalized):
            raise InvalidSkuError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CartQuantity:
    """How many units of one variant a cart line holds (a positive integer).

    ``bool`` is an ``int`` subclass, so it is rejected explicitly -- ``True`` must
    never silently become a quantity of one.
    """

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise InvalidCartQuantityError(self.value)
        if self.value < _MIN_QUANTITY or self.value > _MAX_QUANTITY:
            raise InvalidCartQuantityError(self.value)

    def plus(self, other: CartQuantity) -> CartQuantity:
        """Return the summed quantity, re-validating the upper bound."""
        return CartQuantity(self.value + other.value)

    def capped_sum(self, other: CartQuantity) -> CartQuantity:
        """Return the summed quantity, capped at the maximum instead of raising.

        Unlike ``plus`` -- which rejects an over-large total so a deliberate add/set
        cannot silently exceed the cap -- this is for merging a guest cart into a
        user cart on login, where an absurd combined quantity must degrade to the
        ceiling rather than fail the merge (and therefore the login).
        """
        return CartQuantity(min(self.value + other.value, _MAX_QUANTITY))


@dataclass(frozen=True)
class ChannelRef:
    """A reference to the channel a cart is priced in (by slug).

    The channel lives in another bounded context; whether it exists (and its
    currency) is resolved through a reader port. This value object owns only the
    structural rule that the reference is a non-blank, bounded string.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized or len(normalized) > _CHANNEL_MAX_LENGTH:
            raise InvalidChannelReferenceError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Money:
    """A monetary amount in a single currency (a cart line or whole-cart total).

    Always a fixed-point ``Decimal`` -- never a binary ``float`` -- so the rounding
    surprises that make floats unfit for money cannot occur. Non-negative (an empty
    cart totals zero), finite, and bounded to the stored precision. ``currency`` is a
    three-letter ISO 4217 code, derived from the channel; equality across currencies
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
        # genuine Decimal so a float (or int) never silently becomes money.
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

    @classmethod
    def zero(cls, currency: str) -> Money:
        """Return a zero amount in ``currency`` (the total of an empty cart)."""
        return cls(amount=Decimal("0"), currency=currency)

    def times(self, quantity: CartQuantity) -> Money:
        """Return the amount scaled by an integer quantity (a line total).

        ``Decimal * int`` is exact, so no rounding is introduced. The result is
        re-validated, so an over-large total fails here rather than at the database.
        """
        return Money(amount=self.amount * quantity.value, currency=self.currency)

    def add(self, other: Money) -> Money:
        """Return the sum of two amounts, refusing to add across currencies."""
        if other.currency != self.currency:
            raise InvalidMoneyError(f"cannot add {other.currency!r} to {self.currency!r}")
        return Money(amount=self.amount + other.amount, currency=self.currency)
