"""Value objects for the payment context.

Value objects are immutable and self-validating: an instance cannot exist in an
invalid state, and equality is by value.

Like the order context, the payment context deliberately owns its own ``Money`` rather
than importing the order's or the catalog's: a bounded context depends only on narrow
abstractions of its neighbours, never on their domain types. A payment amount is a
*captured* value (a snapshot of the order total taken at initiation), non-negative and
bounded to the stored precision, and never a binary ``float`` -- fixed-point ``Decimal``
only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from src.domain.payment.exceptions import (
    InvalidMoneyError,
    InvalidOrderReferenceError,
    InvalidPaymentReferenceError,
)

# A payment reference is an opaque, unguessable public handle (never a sequential id,
# which would let one shopper enumerate another's payments). Upper-case alphanumeric with
# dashes, bounded -- the same shape rules the order number uses.
_PAYMENT_REFERENCE_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
_PAYMENT_REFERENCE_MIN_LENGTH = 6
_PAYMENT_REFERENCE_MAX_LENGTH = 40
# The referenced order number mirrors the order context's own shape rules (copied, not
# imported, per the bounded-context rule).
_ORDER_REFERENCE_RE = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
_ORDER_REFERENCE_MIN_LENGTH = 6
_ORDER_REFERENCE_MAX_LENGTH = 40
# Money bounds mirror the order/catalog stored precision (18 total digits, 4 decimal
# places) so a captured amount can always be persisted losslessly.
_MONEY_MAX_DIGITS = 18
_MONEY_MAX_DECIMAL_PLACES = 4
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class PaymentReference:
    """The public, unguessable reference to a payment.

    Deliberately not the database id: a payment reference appears in URLs, so a guessable
    sequential id would let one shopper enumerate another's payments. The generator (a
    port) produces the value; this object owns only its shape.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if (
            len(normalized) < _PAYMENT_REFERENCE_MIN_LENGTH
            or len(normalized) > _PAYMENT_REFERENCE_MAX_LENGTH
            or not _PAYMENT_REFERENCE_RE.match(normalized)
        ):
            raise InvalidPaymentReferenceError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class OrderRef:
    """A reference to the order a payment settles, by its public number.

    The payment context copies the order number's shape rules rather than importing the
    order context's ``OrderNumber`` -- neighbouring contexts are coupled only through
    narrow references, never through each other's domain types.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if (
            len(normalized) < _ORDER_REFERENCE_MIN_LENGTH
            or len(normalized) > _ORDER_REFERENCE_MAX_LENGTH
            or not _ORDER_REFERENCE_RE.match(normalized)
        ):
            raise InvalidOrderReferenceError(self.value)
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Money:
    """A captured monetary amount in a single currency (a payment amount).

    Always a fixed-point ``Decimal`` -- never a binary ``float`` -- so the rounding
    surprises that make floats unfit for money cannot occur. Non-negative, finite, and
    bounded to the stored precision. ``currency`` is a three-letter ISO 4217 code derived
    from the order; equality across currencies is by value.
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

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"


class PaymentMethod(StrEnum):
    """How a shopper pays for an order (a ``str`` enum so it serialises directly).

    * ``COD`` -- cash on delivery: no money moves at checkout; it is collected by the
      courier on hand-over (the capture-on-delivery step belongs to the operations phase).
    * ``CARD_TO_CARD`` -- a manual bank card transfer, verified by staff.
    * ``ONLINE`` -- an Iranian payment gateway (redirect/callback), added in a later slice.

    Only methods with a registered gateway adapter can actually be initiated; the others
    are recognised values that raise ``UnsupportedPaymentMethodError`` until their slice.
    """

    COD = "cod"
    CARD_TO_CARD = "card_to_card"
    ONLINE = "online"


class PaymentStatus(StrEnum):
    """The lifecycle states of a payment (a ``str`` enum so it serialises directly).

    * ``PENDING`` -- initiated, awaiting completion (COD: awaiting collection on delivery;
      online: awaiting the gateway's confirmation).
    * ``AUTHORIZED`` -- funds held but not yet captured (the authorize/void flow).
    * ``CAPTURED`` -- funds captured; this is what drives an order to ``paid``.
    * ``FAILED`` -- the attempt failed (declined, expired, gateway error).
    * ``CANCELLED`` -- abandoned before completion (a pending payment the shopper dropped).
    * ``VOIDED`` -- an authorization released without capture.
    * ``REFUNDED`` -- a captured payment returned to the shopper.
    """

    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    CANCELLED = "cancelled"
    VOIDED = "voided"
    REFUNDED = "refunded"


# The statuses that still "hold" an order: while a payment is in one of these, the order
# has an open payment and a second one must not be initiated. A spent payment
# (failed/cancelled/voided) frees the order for a fresh attempt.
ACTIVE_PAYMENT_STATUSES: frozenset[PaymentStatus] = frozenset(
    {PaymentStatus.PENDING, PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}
)
