"""Integration tests for the order->tax bridge adapter (ConfiguredTaxCalculator).

The adapter computes tax through the tax context and maps it to the order context's own
TaxQuote. A channel that levies no tax calculates ``None`` (so the order captures no tax
line); a taxed channel returns the applied rate and the tax context's rounded amount, never
recomputed by the order context.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pytest_django.fixtures import SettingsWrapper

from src.domain.order.value_objects import Money
from src.infrastructure.order.repositories import ConfiguredTaxCalculator

pytestmark = [pytest.mark.integration]


class TestConfiguredTaxCalculator:
    @pytest.fixture(autouse=True)
    def _configure(self, settings: SettingsWrapper) -> None:
        settings.TAX_RATES = {"ir-main": "9"}

    def test_computes_tax_in_the_order_currency(self) -> None:
        quote = ConfiguredTaxCalculator().calculate(
            channel="ir-main", taxable=Money(Decimal("170000"), "IRR")
        )
        assert quote is not None
        assert quote.rate == Decimal("9")
        assert quote.amount.amount == Decimal("15300")
        assert quote.amount.currency == "IRR"

    def test_an_untaxed_channel_calculates_none(self) -> None:
        assert (
            ConfiguredTaxCalculator().calculate(
                channel="ghost", taxable=Money(Decimal("170000"), "IRR")
            )
            is None
        )

    def test_rounds_half_up_at_the_stored_precision(self) -> None:
        # 33333 * 9% = 2999.97 exactly.
        quote = ConfiguredTaxCalculator().calculate(
            channel="ir-main", taxable=Money(Decimal("33333"), "IRR")
        )
        assert quote is not None
        assert quote.amount.amount == Decimal("2999.97")
