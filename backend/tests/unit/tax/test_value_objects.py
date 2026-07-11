"""Unit tests for the tax value objects (pure Python, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.tax.exceptions import InvalidMoneyError, InvalidTaxRateError
from src.domain.tax.value_objects import Money, TaxRate


class TestMoney:
    def test_accepts_a_non_negative_decimal(self) -> None:
        money = Money(Decimal("50000"), "IRR")
        assert money.amount == Decimal("50000")
        assert money.currency == "IRR"

    def test_normalizes_currency_to_upper_case(self) -> None:
        assert Money(Decimal("1"), "irr").currency == "IRR"

    def test_zero_is_valid(self) -> None:
        assert Money(Decimal("0"), "IRR").amount == Decimal("0")

    @pytest.mark.parametrize("bad", [0, 1, 1.5, "1", None, True])
    def test_rejects_non_decimal_amount(self, bad: object) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(bad, "IRR")  # type: ignore[arg-type]

    def test_rejects_negative_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("-1"), "IRR")

    def test_rejects_non_finite_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("NaN"), "IRR")

    def test_rejects_too_many_decimal_places(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("1.00001"), "IRR")

    def test_rejects_too_many_digits(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("1" * 19), "IRR")

    @pytest.mark.parametrize("bad", ["", "IR", "IRRR", "1RR", "ir1"])
    def test_rejects_malformed_currency(self, bad: str) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("1"), bad)

    def test_equality_is_by_value(self) -> None:
        assert Money(Decimal("1"), "IRR") == Money(Decimal("1"), "irr")


class TestTaxRate:
    def test_accepts_a_whole_percentage(self) -> None:
        assert TaxRate(Decimal("9")).value == Decimal("9")

    def test_accepts_a_fractional_percentage(self) -> None:
        assert TaxRate(Decimal("9.5")).value == Decimal("9.5")

    def test_zero_is_a_valid_tax_free_rate(self) -> None:
        rate = TaxRate(Decimal("0"))
        assert rate.is_zero is True

    def test_hundred_percent_is_the_upper_bound(self) -> None:
        assert TaxRate(Decimal("100")).value == Decimal("100")

    def test_fraction_is_the_multiplier_form(self) -> None:
        assert TaxRate(Decimal("9")).fraction == Decimal("0.09")

    @pytest.mark.parametrize("bad", [9, 9.0, "9", None, True])
    def test_rejects_non_decimal_rate(self, bad: object) -> None:
        with pytest.raises(InvalidTaxRateError):
            TaxRate(bad)  # type: ignore[arg-type]

    def test_rejects_negative_rate(self) -> None:
        with pytest.raises(InvalidTaxRateError):
            TaxRate(Decimal("-1"))

    def test_rejects_rate_above_one_hundred(self) -> None:
        with pytest.raises(InvalidTaxRateError):
            TaxRate(Decimal("100.01"))

    def test_rejects_non_finite_rate(self) -> None:
        with pytest.raises(InvalidTaxRateError):
            TaxRate(Decimal("Infinity"))

    def test_rejects_too_many_decimal_places(self) -> None:
        with pytest.raises(InvalidTaxRateError):
            TaxRate(Decimal("9.00001"))

    def test_is_zero_false_for_a_positive_rate(self) -> None:
        assert TaxRate(Decimal("9")).is_zero is False
