"""Value objects for the order context.

Value objects are immutable and self-validating: an instance cannot exist in an
invalid state, and equality is by value.

Like the cart, the order context deliberately owns its own ``Money``/``Sku`` rather
than importing the catalog's or the cart's: a bounded context depends only on narrow
abstractions of its neighbours, never on their domain types. An order amount is a
*captured* value (a snapshot taken at placement), non-negative and bounded to the
stored precision, and never a binary ``float`` -- fixed-point ``Decimal`` only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from src.domain.order.exceptions import (
    InvalidChannelReferenceError,
    InvalidMoneyError,
    InvalidOrderNumberError,
    InvalidOrderQuantityError,
    InvalidSkuError,
)

# A SKU is upper-cased kebab-case -- the canonical shape the catalog stores, so an
# order line reference always matches regardless of the casing it arrived in.
_SKU_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
_SKU_MAX_LENGTH = 64
_CHANNEL_MAX_LENGTH = 64
# An order number is an opaque, unguessable public reference (never a sequential id,
# which would let one shopper enumerate another's orders). Upper-case alphanumeric
# with dashes, bounded.
_ORDER_NUMBER_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
_ORDER_NUMBER_MIN_LENGTH = 6
_ORDER_NUMBER_MAX_LENGTH = 40
# A line quantity is a positive integer, bounded so an absurd value fails at the
# domain edge rather than at the database.
_MIN_QUANTITY = 1
_MAX_QUANTITY = 1_000_000
# Money bounds mirror the catalog's stored precision (18 total digits, 4 decimal
# places) so a captured total can always be persisted losslessly.
_MONEY_MAX_DIGITS = 18
_MONEY_MAX_DECIMAL_PLACES = 4
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class Sku:
    """A reference to the sold catalog variant, canonicalised to upper case."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if len(normalized) > _SKU_MAX_LENGTH or not _SKU_RE.match(normalized):
            raise InvalidSkuError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class OrderQuantity:
    """How many units of one variant an order line sells (a positive integer).

    ``bool`` is an ``int`` subclass, so it is rejected explicitly -- ``True`` must
    never silently become a quantity of one.
    """

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise InvalidOrderQuantityError(self.value)
        if self.value < _MIN_QUANTITY or self.value > _MAX_QUANTITY:
            raise InvalidOrderQuantityError(self.value)


@dataclass(frozen=True)
class ChannelRef:
    """A reference to the channel an order was placed in (by slug)."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip()
        if not normalized or len(normalized) > _CHANNEL_MAX_LENGTH:
            raise InvalidChannelReferenceError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class OrderNumber:
    """The public, unguessable reference to an order.

    Deliberately not the database id: an order number appears in URLs, so a
    guessable sequential id would let one shopper enumerate another's orders. The
    generator (a port) produces the value; this object owns only its shape.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if (
            len(normalized) < _ORDER_NUMBER_MIN_LENGTH
            or len(normalized) > _ORDER_NUMBER_MAX_LENGTH
            or not _ORDER_NUMBER_RE.match(normalized)
        ):
            raise InvalidOrderNumberError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Money:
    """A captured monetary amount in a single currency (an order line or order total).

    Always a fixed-point ``Decimal`` -- never a binary ``float`` -- so the rounding
    surprises that make floats unfit for money cannot occur. Non-negative, finite, and
    bounded to the stored precision. ``currency`` is a three-letter ISO 4217 code
    derived from the channel; addition across currencies is refused.
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
        """Return a zero amount in ``currency`` (the identity for summing line totals)."""
        return cls(amount=Decimal("0"), currency=currency)

    def times(self, quantity: OrderQuantity) -> Money:
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


class OrderStatus(StrEnum):
    """The lifecycle states of an order (a ``str`` enum so it serialises directly).

    * ``PENDING`` -- placed, stock captured, awaiting payment.
    * ``PAID`` -- payment captured (a later phase drives this transition).
    * ``FULFILLED`` -- shipped/handed over (the operations phase drives this).
    * ``CANCELLED`` -- terminated before fulfilment; captured stock is returned.
    """

    PENDING = "pending"
    PAID = "paid"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
