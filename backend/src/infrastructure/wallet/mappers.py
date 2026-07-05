"""Mapping between the Wallet domain aggregate and its ORM representation."""

from __future__ import annotations

from src.domain.wallet.entities import Wallet, WalletTransaction
from src.domain.wallet.value_objects import Money, TransactionType
from src.infrastructure.wallet.models import WalletModel, WalletTransactionModel


def _owner_id(model: WalletModel) -> str:
    """Rebuild the application's opaque owner id from the wallet's user FK.

    A wallet always belongs to a registered user, so the id is always ``u:<pk>`` -- the same
    encoding the cart/order/payment contexts use, so the domain owns one stable string id.
    """
    return f"u:{model.owner_id}"


def wallet_to_domain(model: WalletModel) -> Wallet:
    """Rebuild the aggregate from a persisted wallet row."""
    return Wallet(
        owner=_owner_id(model),
        balance=Money(amount=model.balance, currency=model.currency_code),
        id=model.pk,
    )


def transaction_to_domain(model: WalletTransactionModel) -> WalletTransaction:
    """Rebuild a ledger entry from a persisted transaction row."""
    return WalletTransaction(
        type=TransactionType(model.type),
        amount=Money(amount=model.amount, currency=model.currency_code),
        reason=model.reason,
        balance_after=Money(amount=model.balance_after, currency=model.currency_code),
        created_at=model.created_at,
        source_reference=model.source_reference,
        id=model.pk,
    )
