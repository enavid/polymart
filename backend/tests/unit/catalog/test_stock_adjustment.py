"""Unit tests for the stock-adjustment domain service (pure domain, no framework)."""

from __future__ import annotations

import pytest

from src.domain.catalog.exceptions import InsufficientStockError, InvalidStockQuantityError
from src.domain.catalog.services import adjust_stock
from src.domain.catalog.value_objects import StockQuantity


class TestAdjustStock:
    def test_a_positive_delta_increases_the_quantity(self) -> None:
        assert adjust_stock(StockQuantity(5), 3) == StockQuantity(8)

    def test_a_negative_delta_decreases_the_quantity(self) -> None:
        assert adjust_stock(StockQuantity(5), -2) == StockQuantity(3)

    def test_a_delta_to_exactly_zero_is_allowed(self) -> None:
        # Selling the last unit is fine; the floor is zero, not below it.
        assert adjust_stock(StockQuantity(5), -5) == StockQuantity(0)

    def test_a_zero_delta_is_a_no_op(self) -> None:
        assert adjust_stock(StockQuantity(5), 0) == StockQuantity(5)

    def test_a_delta_below_zero_is_rejected(self) -> None:
        # Stock can never go negative -- that would be the overselling this guards.
        with pytest.raises(InsufficientStockError):
            adjust_stock(StockQuantity(5), -6)

    def test_a_delta_overflowing_the_maximum_is_rejected(self) -> None:
        with pytest.raises(InvalidStockQuantityError):
            adjust_stock(StockQuantity(2_147_483_647), 1)
