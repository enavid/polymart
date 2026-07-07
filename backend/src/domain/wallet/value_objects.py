"""Value objects for the wallet context.

Value objects are immutable and self-validating: an instance cannot exist in an invalid
state, and equality is by value.

Like the payment and order contexts, the wallet context deliberately owns its own
``Money`` rather than importing a neighbour's: a bounded context depends only on narrow
abstractions of its neighbours, never on their domain types. A wallet balance is a
non-negative, fixed-point ``Decimal`` (never a binary ``float``) so the rounding
surprises that make floats unfit for money cannot occur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from src.domain.wallet.exceptions import (
    InvalidWalletMoneyError,
    WalletCurrencyMismatchError,
)

# Money bounds mirror the payment/order/catalog stored precision (18 total digits, 4
# decimal places) so a balance and any movement persist losslessly.
_MONEY_MAX_DIGITS = 18
_MONEY_MAX_DECIMAL_PLACES = 4
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class Money:
    """A non-negative monetary amount in a single currency (a wallet balance or movement).

    Always a fixed-point ``Decimal`` -- never a binary ``float`` -- non-negative, finite,
    and bounded to the stored precision. ``currency`` is a three-letter ISO 4217 code;
    arithmetic across currencies is refused (``WalletCurrencyMismatchError``).
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        self._validate_amount(self.amount)
        currency = self.currency.strip().upper()
        if not _CURRENCY_RE.match(currency):
            raise InvalidWalletMoneyError(f"currency {self.currency!r}")
        object.__setattr__(self, "currency", currency)

    @staticmethod
    def _validate_amount(amount: Decimal) -> None:
        # bool is an int subclass; Decimal is not -- reject anything that is not a genuine
        # Decimal so a float (or int) never silently becomes money.
        if not isinstance(amount, Decimal):
            raise InvalidWalletMoneyError(f"amount must be a Decimal, got {type(amount).__name__}")
        if not amount.is_finite():
            raise InvalidWalletMoneyError(f"amount not finite: {amount!r}")
        if amount < 0:
            raise InvalidWalletMoneyError(f"amount must not be negative: {amount!r}")
        _sign, digits, exponent = amount.as_tuple()
        if isinstance(exponent, int) and -exponent > _MONEY_MAX_DECIMAL_PLACES:
            raise InvalidWalletMoneyError(
                f"amount has more than {_MONEY_MAX_DECIMAL_PLACES} decimal places: {amount!r}"
            )
        if len(digits) > _MONEY_MAX_DIGITS:
            raise InvalidWalletMoneyError(
                f"amount has more than {_MONEY_MAX_DIGITS} digits: {amount!r}"
            )

    def add(self, other: Money) -> Money:
        """Return the sum with ``other`` (same currency), or raise on a currency mismatch."""
        if self.currency != other.currency:
            raise WalletCurrencyMismatchError(self.currency, other.currency)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def subtract(self, other: Money) -> Money:
        """Return the difference with ``other`` (same currency).

        Raises on a currency mismatch, and -- because ``Money`` is non-negative -- on a
        result below zero. A caller spending a balance must check ``covers`` first, so the
        subtraction can never underflow into an invalid amount.
        """
        if self.currency != other.currency:
            raise WalletCurrencyMismatchError(self.currency, other.currency)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def covers(self, other: Money) -> bool:
        """Whether this amount is at least ``other`` (same currency), i.e. can pay it."""
        if self.currency != other.currency:
            raise WalletCurrencyMismatchError(self.currency, other.currency)
        return self.amount >= other.amount

    def is_positive(self) -> bool:
        """Whether the amount is strictly greater than zero."""
        return self.amount > 0

    def __str__(self) -> str:
        return f"{self.amount} {self.currency}"


class TransactionType(StrEnum):
    """The direction of a wallet ledger entry (a ``str`` enum so it serialises directly).

    * ``CREDIT`` -- value added to the wallet (e.g. a refund to store credit).
    * ``DEBIT`` -- value removed from the wallet (e.g. paying with the balance).
    """

    CREDIT = "credit"
    DEBIT = "debit"
