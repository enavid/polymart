"""Unit tests for the cart pricing domain service (pure Decimal maths, no I/O)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.cart.entities import Cart
from src.domain.cart.exceptions import CurrencyMismatchError
from src.domain.cart.services import price_cart
from src.domain.cart.value_objects import CartQuantity, ChannelRef, Money, Sku


def _cart() -> Cart:
    cart = Cart(owner="7", channel=ChannelRef("ir-main"))
    cart.add_item(Sku("HB-250"), CartQuantity(2))
    cart.add_item(Sku("HB-500"), CartQuantity(1))
    return cart


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="IRR")


class TestPriceCart:
    def test_computes_line_totals_and_cart_total(self) -> None:
        prices = {"HB-250": _money("120000.00"), "HB-500": _money("200000.00")}

        priced = price_cart(_cart(), prices, currency="IRR")

        assert priced.currency == "IRR"
        assert priced.channel == "ir-main"
        assert priced.lines[0].line_total == _money("240000.00")
        assert priced.lines[1].line_total == _money("200000.00")
        assert priced.total == _money("440000.00")

    def test_money_stays_exact_decimal(self) -> None:
        prices = {"HB-250": _money("0.10"), "HB-500": _money("0.20")}

        priced = price_cart(_cart(), prices, currency="IRR")

        # 0.10 * 2 + 0.20 * 1 == 0.40 exactly (a float would drift here).
        assert priced.total.amount == Decimal("0.40")

    def test_an_empty_cart_totals_zero(self) -> None:
        cart = Cart(owner="7", channel=ChannelRef("ir-main"))

        priced = price_cart(cart, {}, currency="IRR")

        assert priced.lines == ()
        assert priced.total == Money.zero("IRR")

    def test_an_unpriced_line_is_marked_unavailable_and_excluded_from_total(self) -> None:
        prices = {"HB-250": _money("120000.00")}  # HB-500 has no price in this channel

        priced = price_cart(_cart(), prices, currency="IRR")

        available = priced.lines[0]
        unavailable = priced.lines[1]
        assert available.available is True
        assert available.line_total == _money("240000.00")
        assert unavailable.available is False
        assert unavailable.unit_price is None
        assert unavailable.line_total is None
        # The total covers only the available line.
        assert priced.total == _money("240000.00")

    def test_a_currency_mismatch_is_refused(self) -> None:
        prices = {"HB-250": Money(amount=Decimal("1"), currency="USD"), "HB-500": _money("1")}

        with pytest.raises(CurrencyMismatchError):
            price_cart(_cart(), prices, currency="IRR")
