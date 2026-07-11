"""Integration tests for the Django wallet repository (real DB).

Cover the aggregate round-trip, the per-wallet source-reference idempotency constraint (the
database backstop against a double refund), owner-scoped reads, and the statement ordering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from src.domain.wallet.entities import Wallet
from src.domain.wallet.value_objects import Money, TransactionType
from src.infrastructure.wallet.models import WalletTransactionModel
from src.infrastructure.wallet.repositories import DjangoWalletRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_AT = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def _owner(phone: str = "09120000001") -> str:
    user = get_user_model().objects.create_user(phone_number=phone, password="pw")
    return f"u:{user.pk}"


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="IRR")


class TestWalletRepository:
    def test_creates_and_reloads_a_wallet(self) -> None:
        repo = DjangoWalletRepository()
        owner = _owner()

        created = repo.create(Wallet.empty(owner=owner, currency="IRR"))

        assert created.id is not None
        reloaded = repo.get_for_owner(owner)
        assert reloaded.owner == owner
        assert reloaded.balance == _money("0")

    def test_save_movement_updates_balance_and_appends_the_ledger(self) -> None:
        repo = DjangoWalletRepository()
        owner = _owner()
        wallet = repo.create(Wallet.empty(owner=owner, currency="IRR"))

        movement = wallet.credit(
            _money("120.50"), reason="refund", source_reference="PAY-A", at=_AT
        )
        stored = repo.save_movement(movement)

        assert stored.id is not None
        assert stored.type == TransactionType.CREDIT
        assert repo.get_for_owner(owner).balance == _money("120.50")
        assert repo.find_transaction_by_source(owner, "PAY-A").amount == _money("120.50")

    def test_source_reference_is_unique_per_wallet(self) -> None:
        repo = DjangoWalletRepository()
        owner = _owner()
        wallet = repo.create(Wallet.empty(owner=owner, currency="IRR"))
        repo.save_movement(
            wallet.credit(_money("10"), reason="refund", source_reference="PAY-A", at=_AT)
        )

        # A second entry with the same source on the same wallet is refused by the DB.
        with pytest.raises(IntegrityError), transaction.atomic():
            repo.save_movement(
                wallet.credit(_money("10"), reason="refund", source_reference="PAY-A", at=_AT)
            )

    def test_null_source_movements_are_not_deduplicated(self) -> None:
        repo = DjangoWalletRepository()
        owner = _owner()
        wallet = repo.create(Wallet.empty(owner=owner, currency="IRR"))

        first = repo.save_movement(
            wallet.credit(_money("10"), reason="adjustment", source_reference=None, at=_AT)
        )
        second = repo.save_movement(
            wallet.credit(_money("5"), reason="adjustment", source_reference=None, at=_AT)
        )

        assert first.id != second.id  # both persisted despite a null source

    def test_list_transactions_is_owner_scoped_and_newest_first(self) -> None:
        repo = DjangoWalletRepository()
        owner = _owner("09120000001")
        other = _owner("09120000002")
        wallet = repo.create(Wallet.empty(owner=owner, currency="IRR"))
        repo.save_movement(
            wallet.credit(_money("10"), reason="refund", source_reference="A", at=_AT)
        )
        after_first = repo.get_for_owner(owner)
        repo.save_movement(
            after_first.credit(_money("20"), reason="refund", source_reference="B", at=_AT)
        )

        entries = repo.list_transactions(owner, limit=50)

        assert [e.source_reference for e in entries] == ["B", "A"]  # newest first
        assert repo.list_transactions(other, limit=50) == ()  # another owner sees nothing
        # Sanity: exactly the two rows exist for this wallet.
        assert WalletTransactionModel.objects.count() == 2

    def test_get_for_owner_is_none_when_no_wallet_exists(self) -> None:
        assert DjangoWalletRepository().get_for_owner(_owner()) is None

    def test_create_is_race_safe_and_returns_the_existing_wallet(self) -> None:
        # Two concurrent first credits for a brand-new-wallet user both find no row to lock
        # and both call create; the second must not raise the OneToOne unique IntegrityError
        # (a transient 500) -- it re-reads and returns the wallet that now exists.
        repo = DjangoWalletRepository()
        owner = _owner()
        first = repo.create(Wallet.empty(owner=owner, currency="IRR"))

        second = repo.create(Wallet.empty(owner=owner, currency="IRR"))

        assert second.id == first.id  # the loser gets the winner's wallet, not an error

    def test_models_have_readable_string_forms(self) -> None:
        from src.infrastructure.wallet.models import WalletModel

        repo = DjangoWalletRepository()
        owner = _owner()
        wallet = repo.create(Wallet.empty(owner=owner, currency="IRR"))
        repo.save_movement(
            wallet.credit(_money("10"), reason="refund", source_reference="PAY-A", at=_AT)
        )

        wallet_model = WalletModel.objects.get(pk=wallet.id)
        transaction_model = wallet_model.transactions.get()
        assert str(wallet_model) == f"wallet:{wallet_model.owner_id}"
        assert "credit" in str(transaction_model)
