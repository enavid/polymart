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
    InvalidCapturedShippingError,
    InvalidChannelReferenceError,
    InvalidMoneyError,
    InvalidOrderNumberError,
    InvalidOrderQuantityError,
    InvalidShippingAddressError,
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
# Shipping-address field bounds mirror the address context's stored precision, since
# the value is a snapshot copied from an already-validated Address -- but the order
# context does not re-enforce Iran-specific phone/postal *formats* (that is the
# address context's concern, not the order context's).
_RECIPIENT_NAME_MAX_LENGTH = 200
_PHONE_NUMBER_MAX_LENGTH = 20
_PROVINCE_MAX_LENGTH = 100
_CITY_MAX_LENGTH = 100
_POSTAL_CODE_MAX_LENGTH = 10
_ADDRESS_LINE_MAX_LENGTH = 255
# The captured shipping method's code/name bounds mirror the shipping context's precision;
# like the address, this is a snapshot copied at placement, so the order context checks only
# presence/length, not the shipping context's own code format.
_SHIPPING_METHOD_CODE_MAX_LENGTH = 32
_SHIPPING_METHOD_NAME_MAX_LENGTH = 120


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


@dataclass(frozen=True)
class ShippingAddress:
    """Where a placed order ships, captured at checkout.

    Like a line's unit price, this is a *snapshot*: it is copied from one of the
    owner's address-book entries at placement time, not referenced by id, so a later
    edit or deletion of that saved address never rewrites a placed order's history.
    """

    recipient_name: str
    phone_number: str
    province: str
    city: str
    postal_code: str
    line1: str
    line2: str | None

    def __post_init__(self) -> None:
        required = (
            ("recipient_name", self.recipient_name, _RECIPIENT_NAME_MAX_LENGTH),
            ("phone_number", self.phone_number, _PHONE_NUMBER_MAX_LENGTH),
            ("province", self.province, _PROVINCE_MAX_LENGTH),
            ("city", self.city, _CITY_MAX_LENGTH),
            ("postal_code", self.postal_code, _POSTAL_CODE_MAX_LENGTH),
            ("line1", self.line1, _ADDRESS_LINE_MAX_LENGTH),
        )
        for name, value, limit in required:
            normalized = value.strip()
            if not normalized or len(normalized) > limit:
                raise InvalidShippingAddressError(f"{name}: {value!r}")
            object.__setattr__(self, name, normalized)

        if self.line2 is not None:
            normalized_line2 = self.line2.strip()
            if not normalized_line2 or len(normalized_line2) > _ADDRESS_LINE_MAX_LENGTH:
                raise InvalidShippingAddressError(f"line2: {self.line2!r}")
            object.__setattr__(self, "line2", normalized_line2)


@dataclass(frozen=True)
class CapturedShipping:
    """The shipping method and its cost, captured onto an order at checkout.

    Like a line's unit price, this is a *snapshot*: the chosen method's code, its display
    name, and its price at placement time are copied onto the order, so a later change to the
    channel's configured rates never rewrites a placed order's history. ``method_code`` is the
    stable key (e.g. ``"standard"``); ``method_name`` is the label shown on the order; ``cost``
    is the flat amount added to the order total.
    """

    method_code: str
    method_name: str
    cost: Money

    def __post_init__(self) -> None:
        code = self.method_code.strip()
        if not code or len(code) > _SHIPPING_METHOD_CODE_MAX_LENGTH:
            raise InvalidCapturedShippingError(f"method_code: {self.method_code!r}")
        name = self.method_name.strip()
        if not name or len(name) > _SHIPPING_METHOD_NAME_MAX_LENGTH:
            raise InvalidCapturedShippingError(f"method_name: {self.method_name!r}")
        object.__setattr__(self, "method_code", code)
        object.__setattr__(self, "method_name", name)
