"""Unit tests for the stock-quantity value object (pure domain, no framework)."""

from __future__ import annotations

import pytest

from src.domain.catalog.exceptions import InvalidStockQuantityError
from src.domain.catalog.value_objects import StockQuantity


class TestStockQuantity:
    def test_accepts_a_non_negative_integer(self) -> None:
        assert StockQuantity(7).value == 7

    def test_accepts_zero(self) -> None:
        # Zero on hand is a legitimate, in-stock-tracked state (out of stock), not an
        # invalid quantity.
        assert StockQuantity(0).value == 0

    def test_rejects_a_negative_quantity(self) -> None:
        with pytest.raises(InvalidStockQuantityError):
            StockQuantity(-1)

    def test_rejects_a_boolean(self) -> None:
        # bool is an int subclass; True must never silently become a quantity of 1.
        with pytest.raises(InvalidStockQuantityError):
            StockQuantity(True)  # type: ignore[arg-type]

    def test_rejects_a_float(self) -> None:
        with pytest.raises(InvalidStockQuantityError):
            StockQuantity(1.5)  # type: ignore[arg-type]

    def test_accepts_the_maximum_quantity(self) -> None:
        assert StockQuantity(2_147_483_647).value == 2_147_483_647

    def test_rejects_a_quantity_above_the_maximum(self) -> None:
        with pytest.raises(InvalidStockQuantityError):
            StockQuantity(2_147_483_648)

    def test_is_immutable(self) -> None:
        quantity = StockQuantity(5)
        with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises FrozenInstanceError
            quantity.value = 6  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert StockQuantity(5) == StockQuantity(5)
