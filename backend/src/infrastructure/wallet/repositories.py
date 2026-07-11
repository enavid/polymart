"""Django ORM implementation of the wallet ports.

The repository persists and reloads the aggregate and its ledger. Every read is scoped to
the owner (always a registered user), so one user can never reach another's wallet. Writes
run inside the caller's transaction, so a balance update and its ledger entry commit as one.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager

from django.db import IntegrityError, transaction

from src.application.wallet.ports import UnitOfWork, WalletRepository
from src.domain.wallet.entities import Wallet, WalletMovement, WalletTransaction
from src.infrastructure.wallet.mappers import transaction_to_domain, wallet_to_domain
from src.infrastructure.wallet.models import WalletModel, WalletTransactionModel

# A wallet owner is always a registered user (``u:<pk>``); guests have no account.
_USER_OWNER_PREFIX = "u:"


def _owner_pk(owner: str) -> int:
    """Map the application's opaque ``u:<pk>`` owner id to the user primary key.

    A wallet has no guest form, so any other shape is a wiring bug, not a runtime input.
    """
    if not owner.startswith(_USER_OWNER_PREFIX):  # pragma: no cover - defensive
        raise ValueError(f"a wallet owner must be a user id: {owner!r}")
    return int(owner[len(_USER_OWNER_PREFIX) :])


class DjangoWalletRepository(WalletRepository):
    """Persist wallets and their ledger with the Django ORM, returning domain aggregates."""

    def get_for_owner(self, owner: str) -> Wallet | None:
        model = WalletModel.objects.filter(owner_id=_owner_pk(owner)).first()
        return None if model is None else wallet_to_domain(model)

    def get_for_update(self, owner: str) -> Wallet | None:
        model = WalletModel.objects.select_for_update().filter(owner_id=_owner_pk(owner)).first()
        return None if model is None else wallet_to_domain(model)

    def create(self, wallet: Wallet) -> Wallet:
        owner_pk = _owner_pk(wallet.owner)
        try:
            # A nested savepoint so a lost create race rolls back just this INSERT, not the
            # caller's whole transaction, leaving the outer atomic() able to continue.
            with transaction.atomic():
                model = WalletModel.objects.create(
                    owner_id=owner_pk,
                    balance=wallet.balance.amount,
                    currency_code=wallet.balance.currency,
                )
        except IntegrityError:
            # Two concurrent first credits for the same brand-new-wallet user both found no
            # row to lock and both reached here; the OneToOne owner constraint let only one
            # win. The loser re-reads the wallet that now exists rather than surfacing a
            # transient 500 -- its credit then proceeds against the shared wallet.
            existing = WalletModel.objects.select_for_update().filter(owner_id=owner_pk).first()
            if existing is None:  # pragma: no cover - the constraint guarantees a row exists
                raise
            return wallet_to_domain(existing)
        return wallet_to_domain(model)

    def save_movement(self, movement: WalletMovement) -> WalletTransaction:
        wallet_id = movement.wallet.id
        if wallet_id is None:  # pragma: no cover - a persisted wallet always carries an id
            raise ValueError("cannot persist a movement for an unsaved wallet")
        WalletModel.objects.filter(pk=wallet_id).update(balance=movement.wallet.balance.amount)
        transaction_model = WalletTransactionModel.objects.create(
            wallet_id=wallet_id,
            type=movement.transaction.type.value,
            amount=movement.transaction.amount.amount,
            currency_code=movement.transaction.amount.currency,
            reason=movement.transaction.reason,
            balance_after=movement.transaction.balance_after.amount,
            source_reference=movement.transaction.source_reference,
            created_at=movement.transaction.created_at,
        )
        return transaction_to_domain(transaction_model)

    def find_transaction_by_source(
        self, owner: str, source_reference: str
    ) -> WalletTransaction | None:
        model = WalletTransactionModel.objects.filter(
            wallet__owner_id=_owner_pk(owner), source_reference=source_reference
        ).first()
        return None if model is None else transaction_to_domain(model)

    def list_transactions(self, owner: str, *, limit: int) -> Sequence[WalletTransaction]:
        models = WalletTransactionModel.objects.filter(wallet__owner_id=_owner_pk(owner)).order_by(
            "-id"
        )[:limit]
        return tuple(transaction_to_domain(model) for model in models)


class DjangoUnitOfWork(UnitOfWork):
    """Transaction boundary backed by Django's ``transaction.atomic``.

    Everything a credit performs inside ``atomic()`` commits together or rolls back together
    on any exception -- so a lost double-credit race or a mid-write failure leaves the balance
    and the ledger consistent (and no partial entry behind).
    """

    def atomic(self) -> AbstractContextManager[None]:
        return transaction.atomic()
