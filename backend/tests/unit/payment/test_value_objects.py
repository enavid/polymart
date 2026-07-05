"""Unit tests for the payment value objects (pure, no DB, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.payment.exceptions import (
    InvalidMoneyError,
    InvalidOrderReferenceError,
    InvalidPaymentReferenceError,
)
from src.domain.payment.value_objects import (
    ACTIVE_PAYMENT_STATUSES,
    Money,
    OrderRef,
    PaymentMethod,
    PaymentReference,
    PaymentStatus,
)

# --- PaymentReference ----------------------------------------------------


class TestPaymentReference:
    def test_normalizes_to_upper_case(self) -> None:
        assert PaymentReference("pay-abc123").value == "PAY-ABC123"

    def test_strips_surrounding_whitespace(self) -> None:
        assert PaymentReference("  PAY-ABC123  ").value == "PAY-ABC123"

    def test_str_is_the_value(self) -> None:
        assert str(PaymentReference("PAY-ABC123")) == "PAY-ABC123"
        assert str(OrderRef("ORD-XYZ789")) == "ORD-XYZ789"

    @pytest.mark.parametrize(
        "bad",
        [
            "",  # empty
            "PAY",  # too short
            "PAY_ABC",  # underscore not allowed
            "PAY ABC",  # space not allowed
            "PAY--ABC",  # empty segment
            "X" * 41,  # too long
        ],
    )
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(InvalidPaymentReferenceError):
            PaymentReference(bad)


# --- OrderRef ------------------------------------------------------------


class TestOrderRef:
    def test_normalizes_to_upper_case(self) -> None:
        assert OrderRef("ord-xyz789").value == "ORD-XYZ789"

    @pytest.mark.parametrize("bad", ["", "ORD", "ORD_1", "x" * 41])
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(InvalidOrderReferenceError):
            OrderRef(bad)


# --- Money ---------------------------------------------------------------


class TestMoney:
    def test_carries_decimal_amount_and_currency(self) -> None:
        money = Money(amount=Decimal("12.50"), currency="IRR")
        assert money.amount == Decimal("12.50")
        assert money.currency == "IRR"

    def test_normalizes_currency_case(self) -> None:
        assert Money(amount=Decimal("1"), currency="irr").currency == "IRR"

    def test_allows_zero(self) -> None:
        assert Money(amount=Decimal("0"), currency="IRR").amount == Decimal("0")

    def test_rejects_negative(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("-1"), currency="IRR")

    def test_rejects_float_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=1.5, currency="IRR")  # type: ignore[arg-type]

    def test_rejects_non_finite(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("NaN"), currency="IRR")

    def test_rejects_too_many_decimal_places(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1.00001"), currency="IRR")

    def test_rejects_too_many_digits(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1234567890123456789"), currency="IRR")  # 19 digits

    def test_str_shows_amount_and_currency(self) -> None:
        assert str(Money(amount=Decimal("12.50"), currency="IRR")) == "12.50 IRR"

    @pytest.mark.parametrize("bad", ["IR", "IRRR", "1RR", ""])
    def test_rejects_malformed_currency(self, bad: str) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1"), currency=bad)

    def test_equality_by_value(self) -> None:
        assert Money(amount=Decimal("5"), currency="IRR") == Money(
            amount=Decimal("5"), currency="IRR"
        )


# --- PaymentMethod / PaymentStatus ---------------------------------------


class TestEnums:
    def test_payment_methods(self) -> None:
        assert PaymentMethod.COD.value == "cod"
        assert PaymentMethod.CARD_TO_CARD.value == "card_to_card"
        assert PaymentMethod.ONLINE.value == "online"

    def test_payment_method_parses_from_value(self) -> None:
        assert PaymentMethod("cod") is PaymentMethod.COD

    def test_payment_method_rejects_unknown(self) -> None:
        with pytest.raises(ValueError):
            PaymentMethod("bitcoin")

    def test_active_statuses_hold_the_order(self) -> None:
        assert {
            PaymentStatus.PENDING,
            PaymentStatus.AUTHORIZED,
            PaymentStatus.CAPTURED,
        } == ACTIVE_PAYMENT_STATUSES

    def test_spent_statuses_are_not_active(self) -> None:
        for spent in (PaymentStatus.FAILED, PaymentStatus.CANCELLED, PaymentStatus.VOIDED):
            assert spent not in ACTIVE_PAYMENT_STATUSES
