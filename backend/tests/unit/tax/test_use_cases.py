"""Unit tests for the tax use cases (against a fake reader, no framework)."""

from __future__ import annotations

from decimal import Decimal

from src.application.tax.ports import TaxRateReader
from src.application.tax.use_cases import CalculateTax, GetTaxRate
from src.domain.tax.value_objects import Money, TaxRate


class FakeTaxRateReader(TaxRateReader):
    """An in-memory reader returning a preset rate (or ``None``) for any channel."""

    def __init__(self, rate: TaxRate | None) -> None:
        self._rate = rate
        self.calls: list[str] = []
        self.seen_classes: list[str] = []

    def rate_for(self, channel: str, tax_class: str = "standard") -> TaxRate | None:
        self.calls.append(channel)
        self.seen_classes.append(tax_class)
        return self._rate


class TestGetTaxRate:
    def test_returns_the_configured_rate(self) -> None:
        reader = FakeTaxRateReader(TaxRate(Decimal("9")))
        assert GetTaxRate(reader).execute(channel="ir-main") == TaxRate(Decimal("9"))

    def test_returns_none_when_untaxed(self) -> None:
        assert GetTaxRate(FakeTaxRateReader(None)).execute(channel="ir-main") is None


class TestCalculateTax:
    def test_computes_the_tax_for_a_taxed_channel(self) -> None:
        reader = FakeTaxRateReader(TaxRate(Decimal("9")))
        result = CalculateTax(reader).execute(
            channel="ir-main", taxable=Money(Decimal("50000"), "IRR")
        )
        assert result is not None
        assert result.rate == TaxRate(Decimal("9"))
        assert result.amount == Money(Decimal("4500"), "IRR")

    def test_returns_none_for_an_untaxed_channel(self) -> None:
        reader = FakeTaxRateReader(None)
        result = CalculateTax(reader).execute(
            channel="ir-main", taxable=Money(Decimal("50000"), "IRR")
        )
        assert result is None

    def test_a_zero_rate_yields_a_zero_amount_result(self) -> None:
        reader = FakeTaxRateReader(TaxRate(Decimal("0")))
        result = CalculateTax(reader).execute(
            channel="ir-main", taxable=Money(Decimal("50000"), "IRR")
        )
        assert result is not None
        assert result.amount == Money(Decimal("0"), "IRR")
