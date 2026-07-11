"""Unit tests for the shipping value objects (pure Python, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.shipping.exceptions import (
    InvalidMoneyError,
    InvalidShippingMethodCodeError,
)
from src.domain.shipping.value_objects import Money, ShippingMethodCode


class TestShippingMethodCode:
    def test_normalizes_to_lower_case(self) -> None:
        assert ShippingMethodCode("Standard").value == "standard"

    def test_accepts_kebab_case(self) -> None:
        assert ShippingMethodCode("in-person").value == "in-person"

    @pytest.mark.parametrize("bad", ["", "  ", "has space", "under_score", "a" * 33, "bad!"])
    def test_rejects_malformed_codes(self, bad: str) -> None:
        with pytest.raises(InvalidShippingMethodCodeError):
            ShippingMethodCode(bad)

    def test_equality_is_by_value(self) -> None:
        assert ShippingMethodCode("EXPRESS") == ShippingMethodCode("express")

    def test_str_is_the_value(self) -> None:
        assert str(ShippingMethodCode("standard")) == "standard"


class TestMoney:
    def test_a_zero_price_is_valid(self) -> None:
        # A free shipping method priced at zero is legitimate.
        assert Money(Decimal("0"), "IRR").amount == Decimal("0")

    def test_normalizes_currency(self) -> None:
        assert Money(Decimal("50000"), "irr").currency == "IRR"

    def test_rejects_a_float_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(50000.0, "IRR")  # type: ignore[arg-type]

    def test_rejects_a_negative_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("-1"), "IRR")

    def test_rejects_too_many_decimal_places(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("1.00001"), "IRR")

    def test_rejects_a_non_finite_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("NaN"), "IRR")

    def test_rejects_too_many_digits(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("1" * 19), "IRR")

    @pytest.mark.parametrize("bad", ["IR", "IRRR", "12R", ""])
    def test_rejects_a_malformed_currency(self, bad: str) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("1"), bad)
