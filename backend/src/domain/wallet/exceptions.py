"""Domain exceptions for the wallet context.

A single base (``WalletError``) lets the transport layer catch the whole family and map
it to a sensible default, while the specific subclasses carry the meaning a view needs to
choose a precise status code.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations


class WalletError(Exception):
    """Base class for every wallet-domain error."""


class InvalidWalletMoneyError(WalletError):
    """Raised when a monetary amount is not a valid, representable, non-negative value."""


class InvalidWalletAmountError(WalletError):
    """Raised when a credit/debit amount is not strictly positive.

    Zero or negative movements are meaningless (a credit adds value, a debit removes it),
    so the aggregate refuses them rather than recording a no-op ledger entry.
    """


class InsufficientWalletFundsError(WalletError):
    """Raised when a debit would take the balance below zero.

    A wallet cannot go into overdraft: spending more than the current balance (or spending
    from a wallet that does not yet exist) is refused before any movement is recorded, so a
    pay-with-wallet attempt that cannot be covered leaves the balance untouched.
    """

    def __init__(self, balance: str, amount: str) -> None:
        super().__init__(f"insufficient funds: balance {balance}, debit {amount}")
        self.balance = balance
        self.amount = amount


class WalletCurrencyMismatchError(WalletError):
    """Raised when a movement's currency does not match the wallet's established currency.

    A wallet holds a single currency (fixed on its first credit); a later movement in a
    different currency cannot be combined with the balance and is refused.
    """

    def __init__(self, wallet_currency: str, movement_currency: str) -> None:
        super().__init__(f"wallet holds {wallet_currency!r}, cannot move {movement_currency!r}")
        self.wallet_currency = wallet_currency
        self.movement_currency = movement_currency
