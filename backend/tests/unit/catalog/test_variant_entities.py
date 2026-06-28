"""Unit tests for the ProductVariant entity's structural rules (pure domain)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import ProductVariant
from src.domain.catalog.exceptions import InvalidVariantNameError
from src.domain.catalog.value_objects import ProductCode, Sku


def _variant(**overrides: object) -> ProductVariant:
    defaults: dict[str, object] = {
        "product": ProductCode("house-blend"),
        "sku": Sku("coffee-250"),
        "name": "250g Bag",
    }
    defaults.update(overrides)
    return ProductVariant(**defaults)  # type: ignore[arg-type]


class TestConstruction:
    def test_pairs_a_product_with_a_sku_and_name(self) -> None:
        variant = _variant()

        assert variant.product.value == "house-blend"
        assert variant.sku.value == "COFFEE-250"
        assert variant.name == "250g Bag"
        assert variant.id is None


class TestName:
    def test_trims_the_name(self) -> None:
        assert _variant(name="  250g Bag  ").name == "250g Bag"

    @pytest.mark.parametrize("raw", ["", "   ", "x" * 256])
    def test_rejects_a_blank_or_overlong_name(self, raw: str) -> None:
        with pytest.raises(InvalidVariantNameError):
            _variant(name=raw)
