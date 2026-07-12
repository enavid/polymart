"""Unit tests for inventory value objects: Quantity and StockSourceCode."""

from __future__ import annotations

import pytest

from src.domain.inventory.exceptions import (
    InvalidQuantityError,
    InvalidStockSourceCodeError,
)
from src.domain.inventory.value_objects import Quantity, StockSourceCode


class TestQuantity:
    def test_accepts_zero(self) -> None:
        assert Quantity(0).value == 0

    def test_accepts_positive(self) -> None:
        assert int(Quantity(42)) == 42

    def test_accepts_stored_maximum(self) -> None:
        assert Quantity(2_147_483_647).value == 2_147_483_647

    def test_rejects_negative(self) -> None:
        with pytest.raises(InvalidQuantityError):
            Quantity(-1)

    def test_rejects_above_maximum(self) -> None:
        with pytest.raises(InvalidQuantityError):
            Quantity(2_147_483_648)

    def test_rejects_non_integer(self) -> None:
        with pytest.raises(InvalidQuantityError):
            Quantity(1.5)  # type: ignore[arg-type]

    def test_rejects_bool(self) -> None:
        # bool is an int subclass; a quantity is a count, not a flag.
        with pytest.raises(InvalidQuantityError):
            Quantity(True)  # type: ignore[arg-type]

    def test_is_immutable(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises FrozenInstanceError
            Quantity(1).value = 2  # type: ignore[misc]


class TestStockSourceCode:
    def test_normalizes_case_and_whitespace(self) -> None:
        assert StockSourceCode("  Main ").value == "main"

    def test_accepts_kebab_case(self) -> None:
        assert StockSourceCode("tehran-dc").value == "tehran-dc"

    def test_str(self) -> None:
        assert str(StockSourceCode("main")) == "main"

    @pytest.mark.parametrize("bad", ["", "  ", "a b", "under_score", "-lead", "trail-", "x" * 33])
    def test_rejects_malformed(self, bad: str) -> None:
        with pytest.raises(InvalidStockSourceCodeError):
            StockSourceCode(bad)
