"""Integration tests for the order->shipping bridge adapter (ConfiguredShippingRateReader).

The adapter resolves a chosen method through the shipping context and maps it to the order
context's own ShippingQuote. It refuses (quotes ``None``) a method the channel does not offer
or one priced in a currency that does not match the resolved order currency, so checkout can
never capture an invented or mismatched rate.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pytest_django.fixtures import SettingsWrapper

from src.infrastructure.order.repositories import ConfiguredShippingRateReader

pytestmark = [pytest.mark.integration]


class TestConfiguredShippingRateReader:
    @pytest.fixture(autouse=True)
    def _configure(self, settings: SettingsWrapper) -> None:
        settings.SHIPPING_METHODS = {
            "ir-main": [
                {
                    "code": "standard",
                    "name": "Standard",
                    "price": "50000",
                    "currency": "IRR",
                    "min_days": 3,
                    "max_days": 5,
                },
                {
                    "code": "dollar",
                    "name": "Cross-border",
                    "price": "10",
                    "currency": "USD",
                    "min_days": 1,
                    "max_days": 2,
                },
            ],
        }

    def test_quotes_a_known_method_in_the_order_currency(self) -> None:
        quote = ConfiguredShippingRateReader().quote(
            channel="ir-main", method_code="standard", currency="IRR"
        )
        assert quote is not None
        assert quote.method_code == "standard"
        assert quote.method_name == "Standard"
        assert quote.cost.amount == Decimal("50000")
        assert quote.cost.currency == "IRR"

    def test_an_unknown_method_quotes_none(self) -> None:
        assert (
            ConfiguredShippingRateReader().quote(
                channel="ir-main", method_code="drone", currency="IRR"
            )
            is None
        )

    def test_a_method_priced_in_another_currency_quotes_none(self) -> None:
        # Configured in USD while the order settles in IRR: it cannot be added to the total,
        # so it is refused rather than capturing a mismatched rate.
        assert (
            ConfiguredShippingRateReader().quote(
                channel="ir-main", method_code="dollar", currency="IRR"
            )
            is None
        )
