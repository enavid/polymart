"""Unit tests for the order value objects (pure, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.order.exceptions import (
    InvalidChannelReferenceError,
    InvalidMoneyError,
    InvalidOrderNumberError,
    InvalidOrderQuantityError,
    InvalidSkuError,
)
from src.domain.order.value_objects import (
    ChannelRef,
    Money,
    OrderNumber,
    OrderQuantity,
    OrderStatus,
    Sku,
)


class TestSku:
    def test_canonicalises_to_upper_case(self) -> None:
        assert Sku("hb-250").value == "HB-250"

    def test_strips_surrounding_whitespace(self) -> None:
        assert Sku("  hb-250 ").value == "HB-250"

    @pytest.mark.parametrize("bad", ["", "hb 250", "hb_250", "-hb", "hb-", "x" * 65])
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(InvalidSkuError):
            Sku(bad)


class TestOrderQuantity:
    def test_accepts_a_positive_integer(self) -> None:
        assert OrderQuantity(3).value == 3

    @pytest.mark.parametrize("bad", [0, -1, 1_000_001])
    def test_rejects_out_of_range(self, bad: int) -> None:
        with pytest.raises(InvalidOrderQuantityError):
            OrderQuantity(bad)

    def test_rejects_bool(self) -> None:
        # bool is an int subclass; True must never become a quantity of one.
        with pytest.raises(InvalidOrderQuantityError):
            OrderQuantity(True)

    def test_rejects_non_integer(self) -> None:
        with pytest.raises(InvalidOrderQuantityError):
            OrderQuantity(2.5)  # type: ignore[arg-type]


class TestChannelRef:
    def test_keeps_a_valid_slug(self) -> None:
        assert ChannelRef("ir-main").value == "ir-main"

    @pytest.mark.parametrize("bad", ["", "   ", "x" * 65])
    def test_rejects_blank_or_too_long(self, bad: str) -> None:
        with pytest.raises(InvalidChannelReferenceError):
            ChannelRef(bad)


class TestOrderNumber:
    def test_canonicalises_to_upper_case(self) -> None:
        assert OrderNumber("ord-abc123").value == "ORD-ABC123"

    @pytest.mark.parametrize("bad", ["", "short", "ord abc", "x" * 41, "ord_1"])
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(InvalidOrderNumberError):
            OrderNumber(bad)


class TestMoney:
    def test_requires_a_decimal_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=1200.0, currency="IRR")  # type: ignore[arg-type]

    def test_rejects_a_negative_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("-1"), currency="IRR")

    def test_rejects_a_non_finite_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("NaN"), currency="IRR")

    def test_rejects_too_many_decimal_places(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1.00001"), currency="IRR")

    def test_rejects_too_many_digits(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1" * 19), currency="IRR")

    @pytest.mark.parametrize("bad", ["ir", "IRRR", "12", ""])
    def test_rejects_a_malformed_currency(self, bad: str) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1"), currency=bad)

    def test_normalises_currency_case(self) -> None:
        assert Money(amount=Decimal("1"), currency="irr").currency == "IRR"

    def test_zero_is_a_zero_amount(self) -> None:
        assert Money.zero("IRR").amount == Decimal("0")

    def test_times_scales_exactly(self) -> None:
        product = Money(amount=Decimal("120000.00"), currency="IRR").times(OrderQuantity(3))
        assert product.amount == Decimal("360000.00")

    def test_add_sums_same_currency(self) -> None:
        result = Money(amount=Decimal("100"), currency="IRR").add(
            Money(amount=Decimal("50"), currency="IRR")
        )
        assert result.amount == Decimal("150")

    def test_add_refuses_currency_mismatch(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1"), currency="IRR").add(
                Money(amount=Decimal("1"), currency="USD")
            )


class TestOrderStatus:
    def test_serialises_to_its_string_value(self) -> None:
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus("cancelled") is OrderStatus.CANCELLED
