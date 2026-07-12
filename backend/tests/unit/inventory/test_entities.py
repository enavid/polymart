"""Unit tests for inventory entities: StockSource and StockLevel."""

from __future__ import annotations

import pytest

from src.domain.inventory.entities import StockLevel, StockPolicy, StockSource
from src.domain.inventory.exceptions import (
    InvalidStockLevelError,
    InvalidStockPolicyError,
    InvalidStockSourceError,
)
from src.domain.inventory.value_objects import Quantity, StockSourceCode


def _level(*, on_hand: int, reserved: int, sku: str = "SKU-1", source: str = "main") -> StockLevel:
    return StockLevel(
        sku=sku,
        source_code=StockSourceCode(source),
        on_hand=Quantity(on_hand),
        reserved=Quantity(reserved),
    )


class TestStockSource:
    def test_valid(self) -> None:
        source = StockSource(code=StockSourceCode("main"), name="  Main Warehouse ")
        assert source.name == "Main Warehouse"

    @pytest.mark.parametrize("bad_name", ["", "   ", "x" * 101])
    def test_rejects_bad_name(self, bad_name: str) -> None:
        with pytest.raises(InvalidStockSourceError):
            StockSource(code=StockSourceCode("main"), name=bad_name)


class TestStockLevel:
    def test_available_is_on_hand_minus_reserved(self) -> None:
        assert _level(on_hand=10, reserved=3).available == 7

    def test_available_zero_when_fully_reserved(self) -> None:
        assert _level(on_hand=5, reserved=5).available == 0

    def test_available_zero_when_empty(self) -> None:
        assert _level(on_hand=0, reserved=0).available == 0

    def test_rejects_reserved_over_on_hand(self) -> None:
        # The core invariant: you cannot reserve more than physically exists.
        with pytest.raises(InvalidStockLevelError):
            _level(on_hand=3, reserved=4)


class TestStockPolicy:
    def test_defaults_to_no_backorder_no_alert(self) -> None:
        policy = StockPolicy(sku="SKU-1")
        assert policy.backorderable is False
        assert policy.low_stock_threshold == 0
        assert policy.backordered == Quantity(0)
        assert policy.has_backorder is False

    def test_has_backorder_when_units_are_promised_beyond_stock(self) -> None:
        policy = StockPolicy(sku="SKU-1", backorderable=True, backordered=Quantity(3))
        assert policy.has_backorder is True

    def test_rejects_a_negative_threshold(self) -> None:
        with pytest.raises(InvalidStockPolicyError):
            StockPolicy(sku="SKU-1", low_stock_threshold=-1)
