"""Unit tests for the cart value objects (pure domain, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.cart.exceptions import (
    InvalidCartQuantityError,
    InvalidChannelReferenceError,
    InvalidMoneyError,
    InvalidSkuError,
)
from src.domain.cart.value_objects import CartQuantity, ChannelRef, Money, Sku


class TestSku:
    def test_canonicalises_to_upper_case(self) -> None:
        assert Sku("hb-250").value == "HB-250"

    def test_strips_surrounding_whitespace(self) -> None:
        assert Sku("  hb-250  ").value == "HB-250"

    @pytest.mark.parametrize("bad", ["", "  ", "hb 250", "hb_250", "-hb", "hb-", "x" * 65])
    def test_rejects_a_malformed_sku(self, bad: str) -> None:
        with pytest.raises(InvalidSkuError):
            Sku(bad)

    def test_str_is_the_canonical_value(self) -> None:
        assert str(Sku("hb-250")) == "HB-250"


class TestCartQuantity:
    def test_accepts_a_positive_integer(self) -> None:
        assert CartQuantity(3).value == 3

    @pytest.mark.parametrize("bad", [0, -1, 1_000_001])
    def test_rejects_out_of_range(self, bad: int) -> None:
        with pytest.raises(InvalidCartQuantityError):
            CartQuantity(bad)

    def test_rejects_a_boolean(self) -> None:
        with pytest.raises(InvalidCartQuantityError):
            CartQuantity(True)  # bool is an int subclass -- must not become quantity 1

    def test_rejects_a_non_integer(self) -> None:
        with pytest.raises(InvalidCartQuantityError):
            CartQuantity(2.5)  # type: ignore[arg-type]

    def test_plus_sums_two_quantities(self) -> None:
        assert CartQuantity(2).plus(CartQuantity(3)) == CartQuantity(5)

    def test_plus_re_validates_the_upper_bound(self) -> None:
        with pytest.raises(InvalidCartQuantityError):
            CartQuantity(1_000_000).plus(CartQuantity(1))

    def test_capped_sum_sums_two_quantities(self) -> None:
        assert CartQuantity(2).capped_sum(CartQuantity(3)) == CartQuantity(5)

    def test_capped_sum_caps_at_the_maximum_instead_of_raising(self) -> None:
        # Unlike plus(), a merge must degrade gracefully rather than fail a login.
        assert CartQuantity(1_000_000).capped_sum(CartQuantity(5)) == CartQuantity(1_000_000)


class TestChannelRef:
    def test_accepts_and_strips_a_reference(self) -> None:
        assert ChannelRef("  ir-main  ").value == "ir-main"

    @pytest.mark.parametrize("bad", ["", "   ", "x" * 65])
    def test_rejects_blank_or_too_long(self, bad: str) -> None:
        with pytest.raises(InvalidChannelReferenceError):
            ChannelRef(bad)

    def test_str_is_the_value(self) -> None:
        assert str(ChannelRef("ir-main")) == "ir-main"


class TestMoney:
    def test_accepts_a_non_negative_decimal(self) -> None:
        money = Money(amount=Decimal("120000.50"), currency="irr")
        assert money.amount == Decimal("120000.50")
        assert money.currency == "IRR"

    def test_allows_zero(self) -> None:
        assert Money.zero("IRR").amount == Decimal("0")

    def test_rejects_a_float_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=1.5, currency="IRR")  # type: ignore[arg-type]

    def test_rejects_a_negative_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("-1"), currency="IRR")

    def test_rejects_over_precision(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1.234567"), currency="IRR")

    def test_rejects_a_non_finite_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("Infinity"), currency="IRR")

    def test_rejects_too_many_digits(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1" * 19), currency="IRR")

    def test_rejects_a_malformed_currency(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1"), currency="rial")

    def test_times_scales_exactly_by_quantity(self) -> None:
        result = Money(amount=Decimal("120000.25"), currency="IRR").times(CartQuantity(3))
        assert result.amount == Decimal("360000.75")

    def test_add_sums_same_currency(self) -> None:
        result = Money(amount=Decimal("10"), currency="IRR").add(
            Money(amount=Decimal("5"), currency="IRR")
        )
        assert result.amount == Decimal("15")

    def test_add_refuses_across_currencies(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("10"), currency="IRR").add(
                Money(amount=Decimal("5"), currency="USD")
            )
