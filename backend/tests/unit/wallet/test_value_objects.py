"""Unit tests for the wallet value objects (pure, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.wallet.exceptions import (
    InvalidWalletMoneyError,
    WalletCurrencyMismatchError,
)
from src.domain.wallet.value_objects import Money, TransactionType


class TestMoney:
    def test_accepts_a_non_negative_decimal(self) -> None:
        money = Money(amount=Decimal("1250.5000"), currency="irr")
        assert money.amount == Decimal("1250.5000")
        assert money.currency == "IRR"  # normalised upper-case

    def test_zero_is_valid(self) -> None:
        assert Money(amount=Decimal("0"), currency="IRR").amount == Decimal("0")

    def test_rejects_a_float_amount(self) -> None:
        with pytest.raises(InvalidWalletMoneyError):
            Money(amount=1250.5, currency="IRR")  # type: ignore[arg-type]

    def test_rejects_a_negative_amount(self) -> None:
        with pytest.raises(InvalidWalletMoneyError):
            Money(amount=Decimal("-1"), currency="IRR")

    def test_rejects_a_non_finite_amount(self) -> None:
        with pytest.raises(InvalidWalletMoneyError):
            Money(amount=Decimal("NaN"), currency="IRR")

    def test_rejects_too_many_decimal_places(self) -> None:
        with pytest.raises(InvalidWalletMoneyError):
            Money(amount=Decimal("1.00001"), currency="IRR")

    def test_rejects_too_many_digits(self) -> None:
        with pytest.raises(InvalidWalletMoneyError):
            Money(amount=Decimal("1" * 19), currency="IRR")

    def test_rejects_a_malformed_currency(self) -> None:
        with pytest.raises(InvalidWalletMoneyError):
            Money(amount=Decimal("1"), currency="TOMAN")

    def test_add_sums_same_currency(self) -> None:
        total = Money(amount=Decimal("100"), currency="IRR").add(
            Money(amount=Decimal("50"), currency="IRR")
        )
        assert total == Money(amount=Decimal("150"), currency="IRR")

    def test_add_refuses_a_currency_mismatch(self) -> None:
        with pytest.raises(WalletCurrencyMismatchError):
            Money(amount=Decimal("100"), currency="IRR").add(
                Money(amount=Decimal("50"), currency="USD")
            )

    def test_is_positive(self) -> None:
        assert Money(amount=Decimal("1"), currency="IRR").is_positive()
        assert not Money(amount=Decimal("0"), currency="IRR").is_positive()

    def test_subtract_reduces_same_currency(self) -> None:
        remaining = Money(amount=Decimal("150"), currency="IRR").subtract(
            Money(amount=Decimal("50"), currency="IRR")
        )
        assert remaining == Money(amount=Decimal("100"), currency="IRR")

    def test_subtract_to_exactly_zero(self) -> None:
        remaining = Money(amount=Decimal("50"), currency="IRR").subtract(
            Money(amount=Decimal("50"), currency="IRR")
        )
        assert remaining == Money(amount=Decimal("0"), currency="IRR")

    def test_subtract_refuses_a_currency_mismatch(self) -> None:
        with pytest.raises(WalletCurrencyMismatchError):
            Money(amount=Decimal("100"), currency="IRR").subtract(
                Money(amount=Decimal("50"), currency="USD")
            )

    def test_subtract_below_zero_is_rejected_by_money(self) -> None:
        # A subtraction that would go negative cannot form a valid (non-negative) Money;
        # callers must guard with covers() first.
        with pytest.raises(InvalidWalletMoneyError):
            Money(amount=Decimal("50"), currency="IRR").subtract(
                Money(amount=Decimal("51"), currency="IRR")
            )

    def test_covers_is_true_when_at_least_the_other(self) -> None:
        balance = Money(amount=Decimal("150"), currency="IRR")
        assert balance.covers(Money(amount=Decimal("150"), currency="IRR"))
        assert balance.covers(Money(amount=Decimal("100"), currency="IRR"))

    def test_covers_is_false_when_less_than_the_other(self) -> None:
        balance = Money(amount=Decimal("150"), currency="IRR")
        assert not balance.covers(Money(amount=Decimal("151"), currency="IRR"))

    def test_covers_refuses_a_currency_mismatch(self) -> None:
        with pytest.raises(WalletCurrencyMismatchError):
            Money(amount=Decimal("150"), currency="IRR").covers(
                Money(amount=Decimal("50"), currency="USD")
            )

    def test_str(self) -> None:
        assert str(Money(amount=Decimal("10"), currency="IRR")) == "10 IRR"

    def test_equality_is_by_value(self) -> None:
        assert Money(amount=Decimal("10"), currency="IRR") == Money(
            amount=Decimal("10"), currency="IRR"
        )


class TestTransactionType:
    def test_serialises_to_its_value(self) -> None:
        assert TransactionType.CREDIT == "credit"
        assert TransactionType.DEBIT == "debit"
