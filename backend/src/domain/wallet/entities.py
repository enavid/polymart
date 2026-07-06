"""The Wallet aggregate: a shopper's store of internal credit, with an append-only ledger.

A wallet holds a single-currency balance and produces an immutable ledger entry for every
movement. In this slice the only movement is a *credit* (a refund converted to store
credit); the aggregate is immutable, so a credit yields a new ``Wallet`` plus the
``WalletTransaction`` that recorded it, never mutating in place.

Identity is the opaque, prefixed owner id the cart/order/payment contexts already use
(``u:<pk>`` -- a wallet always belongs to a registered user, never a guest). Time is
injected (``at``) so the domain stays pure and testable.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal

from src.domain.wallet.exceptions import (
    InsufficientWalletFundsError,
    InvalidWalletAmountError,
)
from src.domain.wallet.value_objects import Money, TransactionType


@dataclass(frozen=True)
class WalletTransaction:
    """One append-only ledger entry: a single movement of value on a wallet.

    ``balance_after`` is the wallet's balance once this movement was applied, captured so a
    statement can be rendered without replaying the whole ledger. ``source_reference`` ties
    the entry to what caused it (a payment reference for a refund) and is the idempotency
    key -- a second movement carrying the same source must never be recorded twice.
    """

    type: TransactionType
    amount: Money
    reason: str
    balance_after: Money
    created_at: datetime
    source_reference: str | None = field(default=None)
    id: int | None = field(default=None)


@dataclass(frozen=True)
class WalletMovement:
    """The outcome of a balance change: the updated wallet and the entry it produced.

    Returned together so the application layer persists the new balance and appends the
    ledger entry as one unit, keeping the two consistent.
    """

    wallet: Wallet
    transaction: WalletTransaction


@dataclass(frozen=True)
class Wallet:
    """A user's internal-credit balance in a single currency.

    Immutable: a credit returns a new ``Wallet`` (via ``WalletMovement``) rather than
    mutating in place, so the aggregate never sits in a half-changed state.
    """

    owner: str
    balance: Money
    id: int | None = field(default=None)

    @staticmethod
    def empty(*, owner: str, currency: str) -> Wallet:
        """A brand-new wallet with a zero balance, minted lazily on the first credit."""
        return Wallet(owner=owner, balance=Money(amount=Decimal("0"), currency=currency))

    def credit(
        self,
        amount: Money,
        *,
        reason: str,
        source_reference: str | None,
        at: datetime,
    ) -> WalletMovement:
        """Add ``amount`` to the balance and record the credit.

        The amount must be strictly positive (a zero/negative credit is meaningless) and in
        the wallet's currency (``Money.add`` refuses a mismatch). Returns the credited wallet
        together with the ledger entry that recorded the movement.
        """
        if not amount.is_positive():
            raise InvalidWalletAmountError(f"credit amount must be positive: {amount.amount!r}")
        new_balance = self.balance.add(amount)
        credited = replace(self, balance=new_balance)
        transaction = WalletTransaction(
            type=TransactionType.CREDIT,
            amount=amount,
            reason=reason,
            balance_after=new_balance,
            created_at=at,
            source_reference=source_reference,
        )
        return WalletMovement(wallet=credited, transaction=transaction)

    def debit(
        self,
        amount: Money,
        *,
        reason: str,
        source_reference: str | None,
        at: datetime,
    ) -> WalletMovement:
        """Remove ``amount`` from the balance and record the debit.

        The amount must be strictly positive and in the wallet's currency, and the balance
        must cover it -- a wallet never goes into overdraft, so an uncovered debit raises
        ``InsufficientWalletFundsError`` before any movement is produced. Returns the debited
        wallet together with the ledger entry that recorded the movement.
        """
        if not amount.is_positive():
            raise InvalidWalletAmountError(f"debit amount must be positive: {amount.amount!r}")
        if not self.balance.covers(amount):
            raise InsufficientWalletFundsError(
                balance=str(self.balance.amount), amount=str(amount.amount)
            )
        new_balance = self.balance.subtract(amount)
        debited = replace(self, balance=new_balance)
        transaction = WalletTransaction(
            type=TransactionType.DEBIT,
            amount=amount,
            reason=reason,
            balance_after=new_balance,
            created_at=at,
            source_reference=source_reference,
        )
        return WalletMovement(wallet=debited, transaction=transaction)
