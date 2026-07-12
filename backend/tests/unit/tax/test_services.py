"""Unit tests for the tax domain service (pure Python, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.tax.services import calculate_tax
from src.domain.tax.value_objects import Money, TaxRate


class TestCalculateTax:
    def test_computes_a_whole_percentage_exactly(self) -> None:
        tax = calculate_tax(Money(Decimal("50000"), "IRR"), TaxRate(Decimal("9")))
        assert tax == Money(Decimal("4500"), "IRR")

    def test_zero_rate_yields_zero_tax(self) -> None:
        tax = calculate_tax(Money(Decimal("50000"), "IRR"), TaxRate(Decimal("0")))
        assert tax == Money(Decimal("0"), "IRR")

    def test_zero_base_yields_zero_tax(self) -> None:
        tax = calculate_tax(Money(Decimal("0"), "IRR"), TaxRate(Decimal("9")))
        assert tax == Money(Decimal("0"), "IRR")

    def test_preserves_the_taxable_currency(self) -> None:
        tax = calculate_tax(Money(Decimal("100"), "USD"), TaxRate(Decimal("10")))
        assert tax.currency == "USD"

    def test_rounds_half_up_at_the_stored_precision(self) -> None:
        # 12345 * 9% = 1111.05 exactly -- representable, no rounding needed.
        assert calculate_tax(Money(Decimal("12345"), "IRR"), TaxRate(Decimal("9"))) == Money(
            Decimal("1111.05"), "IRR"
        )

    def test_rounds_half_up_when_the_fifth_decimal_forces_it(self) -> None:
        # 1.23455 * 10% = 0.123455 -> quantized half-up to 4 dp = 0.1235.
        tax = calculate_tax(Money(Decimal("1.2346"), "IRR"), TaxRate(Decimal("10")))
        assert tax.amount == Decimal("0.1235")

    def test_result_is_representable_as_money(self) -> None:
        # A fractional rate on a large base still quantizes to <= 4 dp (no InvalidMoneyError).
        tax = calculate_tax(Money(Decimal("999999.9999"), "IRR"), TaxRate(Decimal("9.5")))
        _sign, _digits, exponent = tax.amount.as_tuple()
        assert isinstance(exponent, int) and -exponent <= 4

    @pytest.mark.parametrize(
        ("base", "rate", "expected"),
        [
            (Decimal("50000"), Decimal("10"), Decimal("5000")),
            (Decimal("170000"), Decimal("9"), Decimal("15300")),
            (Decimal("33333"), Decimal("9"), Decimal("2999.97")),
        ],
    )
    def test_table_of_known_values(self, base: Decimal, rate: Decimal, expected: Decimal) -> None:
        assert calculate_tax(Money(base, "IRR"), TaxRate(rate)).amount == expected
