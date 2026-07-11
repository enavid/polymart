"""Unit tests for the order domain services (pure, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.order.exceptions import InvalidMoneyError
from src.domain.order.services import PricedItem, build_order_lines, order_total
from src.domain.order.value_objects import Money, OrderQuantity, Sku


def _item(sku: str, qty: int, unit: str, currency: str = "IRR") -> PricedItem:
    return PricedItem(
        sku=Sku(sku),
        quantity=OrderQuantity(qty),
        unit_price=Money(amount=Decimal(unit), currency=currency),
    )


class TestBuildOrderLines:
    def test_computes_each_line_total_exactly(self) -> None:
        lines = build_order_lines([_item("HB-250", 3, "120000.00")])
        assert lines[0].line_total.amount == Decimal("360000.00")

    def test_preserves_the_order_of_items(self) -> None:
        lines = build_order_lines([_item("HB-250", 1, "1"), _item("DR-250", 1, "2")])
        assert [line.sku.value for line in lines] == ["HB-250", "DR-250"]


class TestOrderTotal:
    def test_sums_the_line_totals(self) -> None:
        lines = build_order_lines(
            [_item("HB-250", 2, "120000.00"), _item("DR-250", 1, "150000.00")]
        )
        assert order_total(lines, "IRR").amount == Decimal("390000.00")

    def test_an_empty_order_totals_zero(self) -> None:
        assert order_total([], "IRR").amount == Decimal("0")

    def test_refuses_to_mix_currencies(self) -> None:
        lines = build_order_lines([_item("HB-250", 1, "1", "USD")])
        with pytest.raises(InvalidMoneyError):
            order_total(lines, "IRR")

    def test_adds_the_shipping_cost_to_the_grand_total(self) -> None:
        lines = build_order_lines([_item("HB-250", 2, "120000.00")])
        shipping = Money(amount=Decimal("50000.00"), currency="IRR")
        assert order_total(lines, "IRR", shipping).amount == Decimal("290000.00")

    def test_omitting_shipping_keeps_the_goods_total(self) -> None:
        lines = build_order_lines([_item("HB-250", 1, "120000.00")])
        assert order_total(lines, "IRR").amount == Decimal("120000.00")

    def test_refuses_shipping_in_another_currency(self) -> None:
        lines = build_order_lines([_item("HB-250", 1, "120000.00")])
        shipping = Money(amount=Decimal("50000.00"), currency="USD")
        with pytest.raises(InvalidMoneyError):
            order_total(lines, "IRR", shipping)
