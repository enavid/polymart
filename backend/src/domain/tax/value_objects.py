"""Value objects for the tax context.

Value objects are immutable and self-validating: an instance cannot exist in an invalid
state, and equality is by value. Like every other bounded context, tax owns its own
``Money`` rather than importing a neighbour's -- a context depends on narrow abstractions of
its neighbours, never on their domain types. A taxable amount is a fixed-point ``Decimal``
(never a binary ``float``), non-negative, and bounded to the stored precision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from src.domain.tax.exceptions import InvalidMoneyError, InvalidTaxRateError

# Money precision mirrors the order/catalog stored precision (18 total digits, 4 decimal
# places) so a computed tax amount is always captured onto an order losslessly.
_MONEY_MAX_DIGITS = 18
_MONEY_MAX_DECIMAL_PLACES = 4
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
# A tax rate is a percentage: 0 (tax-free) up to 100. Anything above 100 is a configuration
# bug (a rate is not a multiplier). Bounded to a few decimal places so a fractional rate such
# as 9.5% is representable while an absurd precision is refused at the domain edge.
_RATE_MAX = Decimal("100")
_RATE_MAX_DECIMAL_PLACES = 4


@dataclass(frozen=True)
class Money:
    """A taxable monetary amount (or a computed tax amount) in a single currency.

    Always a fixed-point ``Decimal`` -- never a binary ``float`` -- so rounding surprises
    cannot occur. Non-negative, finite, and bounded to the stored precision. ``currency`` is
    a three-letter ISO 4217 code derived from the channel.
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
class TaxRate:
    """A tax rate expressed as a percentage (e.g. ``Decimal("9")`` for 9% VAT).

    A fixed-point ``Decimal`` in ``[0, 100]``: zero is a legitimate tax-free rate; a value
    above 100 is rejected as a misconfiguration (a rate is a percentage, not a multiplier).
    ``fraction`` gives the multiplier form (rate / 100) for the tax calculation.
    """

    value: Decimal

    def __post_init__(self) -> None:
        # bool is an int subclass; Decimal is not -- reject anything that is not a genuine
        # Decimal so a float never silently becomes a rate.
        if not isinstance(self.value, Decimal):
            raise InvalidTaxRateError(f"rate must be a Decimal, got {type(self.value).__name__}")
        if not self.value.is_finite():
            raise InvalidTaxRateError(f"rate not finite: {self.value!r}")
        if self.value < 0 or self.value > _RATE_MAX:
            raise InvalidTaxRateError(f"rate out of range [0, 100]: {self.value!r}")
        _sign, _digits, exponent = self.value.as_tuple()
        if isinstance(exponent, int) and -exponent > _RATE_MAX_DECIMAL_PLACES:
            raise InvalidTaxRateError(
                f"rate has more than {_RATE_MAX_DECIMAL_PLACES} decimal places: {self.value!r}"
            )

    @property
    def is_zero(self) -> bool:
        """Whether this rate levies no tax (a channel with a zero rate charges nothing)."""
        return self.value == 0

    @property
    def fraction(self) -> Decimal:
        """The rate as a multiplier (percentage / 100), for the tax calculation."""
        return self.value / Decimal("100")
