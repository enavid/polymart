"""Unit tests for the variant value objects (pure domain, no Django)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.domain.catalog.exceptions import InvalidSkuError
from src.domain.catalog.value_objects import Sku


class TestSku:
    def test_accepts_an_uppercase_stock_keeping_code(self) -> None:
        assert Sku("COFFEE-250").value == "COFFEE-250"

    def test_canonicalizes_to_uppercase(self) -> None:
        # A SKU is a single stock-keeping identity; case must not split it in two.
        assert Sku("coffee-250").value == "COFFEE-250"

    def test_trims_surrounding_whitespace(self) -> None:
        assert Sku("  coffee-250  ").value == "COFFEE-250"

    def test_str_is_the_code(self) -> None:
        assert str(Sku("coffee-250")) == "COFFEE-250"

    @pytest.mark.parametrize(
        "raw",
        ["", "  ", "has space", "trailing-", "-leading", "under_score", "dot.dot", "A" * 65],
    )
    def test_rejects_malformed_codes(self, raw: str) -> None:
        with pytest.raises(InvalidSkuError):
            Sku(raw)

    def test_is_immutable(self) -> None:
        with pytest.raises(FrozenInstanceError):
            Sku("coffee-250").value = "tea"  # type: ignore[misc]
