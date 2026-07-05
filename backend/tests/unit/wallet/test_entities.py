"""Unit tests for the Wallet aggregate (pure, no framework)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.wallet.entities import Wallet
from src.domain.wallet.exceptions import (
    InvalidWalletAmountError,
    WalletCurrencyMismatchError,
)
from src.domain.wallet.value_objects import Money, TransactionType

_AT = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def _money(amount: str, currency: str = "IRR") -> Money:
    return Money(amount=Decimal(amount), currency=currency)


class TestEmptyWallet:
    def test_starts_with_a_zero_balance(self) -> None:
        wallet = Wallet.empty(owner="u:7", currency="IRR")
        assert wallet.owner == "u:7"
        assert wallet.balance == _money("0")
        assert wallet.id is None


class TestCredit:
    def test_increases_the_balance_and_records_a_ledger_entry(self) -> None:
        wallet = Wallet.empty(owner="u:7", currency="IRR")

        movement = wallet.credit(
            _money("1250.5000"), reason="refund", source_reference="PAY-ABC", at=_AT
        )

        assert movement.wallet.balance == _money("1250.5000")
        # The original aggregate is unchanged (immutability).
        assert wallet.balance == _money("0")
        txn = movement.transaction
        assert txn.type == TransactionType.CREDIT
        assert txn.amount == _money("1250.5000")
        assert txn.reason == "refund"
        assert txn.source_reference == "PAY-ABC"
        assert txn.balance_after == _money("1250.5000")
        assert txn.created_at == _AT

    def test_accumulates_across_multiple_credits(self) -> None:
        wallet = Wallet.empty(owner="u:7", currency="IRR")
        first = wallet.credit(_money("100"), reason="refund", source_reference="A", at=_AT)
        second = first.wallet.credit(_money("50"), reason="refund", source_reference="B", at=_AT)
        assert second.wallet.balance == _money("150")
        assert second.transaction.balance_after == _money("150")

    def test_rejects_a_zero_credit(self) -> None:
        wallet = Wallet.empty(owner="u:7", currency="IRR")
        with pytest.raises(InvalidWalletAmountError):
            wallet.credit(_money("0"), reason="refund", source_reference=None, at=_AT)

    def test_rejects_a_currency_mismatch(self) -> None:
        wallet = Wallet.empty(owner="u:7", currency="IRR")
        with pytest.raises(WalletCurrencyMismatchError):
            wallet.credit(_money("1", "USD"), reason="refund", source_reference=None, at=_AT)

    def test_source_reference_is_optional(self) -> None:
        wallet = Wallet.empty(owner="u:7", currency="IRR")
        movement = wallet.credit(_money("10"), reason="adjustment", source_reference=None, at=_AT)
        assert movement.transaction.source_reference is None
