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
from dataclasses import dataclass
from decimal import Decimal

from src.domain.shipping.exceptions import (
    InvalidMoneyError,
    InvalidShippingMethodCodeError,
)

# A method code is lower-case kebab-case ("standard", "express", "in-person") -- the stable
# key a channel's config and the checkout selection both reference.
_CODE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CODE_MAX_LENGTH = 32
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
