"""Integration tests for the catalog stock bridge onto the inventory context (real DB).

``DjangoStockRepository`` keeps the catalog's simple single-count surface but stores the
count as an on-hand level on the inventory context's default source, so these tests assert
the round-trip behaviour and the backing ``inventory_stock_level`` row.
"""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Product, ProductType, ProductVariant
from src.domain.catalog.exceptions import InsufficientStockError, VariantNotFoundError
from src.domain.catalog.value_objects import (
    ProductCode,
    ProductTypeCode,
    Sku,
    StockQuantity,
)
from src.infrastructure.catalog.repositories import (
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoStockRepository,
    DjangoVariantRepository,
)
from src.infrastructure.inventory.models import StockLevelModel

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed_variant(sku: str = "HB-250") -> None:
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
    DjangoProductRepository().add(
        Product(
            code=ProductCode("house-blend"),
            name="House Blend",
            product_type=ProductTypeCode("coffee"),
        )
    )
    DjangoVariantRepository().add(
        ProductVariant(product=ProductCode("house-blend"), sku=Sku(sku), name="House Blend 250g")
    )


class TestSetQuantity:
    def test_stores_the_quantity(self) -> None:
        _seed_variant()
        repo = DjangoStockRepository()

        result = repo.set_quantity("HB-250", StockQuantity(12))

        assert result == StockQuantity(12)
        level = StockLevelModel.objects.get(sku="HB-250", source__code="main")
        assert level.on_hand == 12

    def test_setting_again_overwrites_without_a_second_row(self) -> None:
        _seed_variant()
        repo = DjangoStockRepository()
        repo.set_quantity("HB-250", StockQuantity(12))

        repo.set_quantity("HB-250", StockQuantity(3))

        assert StockLevelModel.objects.filter(sku="HB-250").count() == 1
        assert repo.get_quantity("HB-250") == StockQuantity(3)

    def test_raises_for_an_unknown_variant(self) -> None:
        with pytest.raises(VariantNotFoundError):
            DjangoStockRepository().set_quantity("GHOST", StockQuantity(1))


class TestAdjustQuantity:
    def test_accumulates_sequential_adjustments(self) -> None:
        _seed_variant()
        repo = DjangoStockRepository()
        repo.set_quantity("HB-250", StockQuantity(10))

        repo.adjust_quantity("HB-250", 5)
        result = repo.adjust_quantity("HB-250", -3)

        assert result == StockQuantity(12)
        assert repo.get_quantity("HB-250") == StockQuantity(12)

    def test_adjusting_a_variant_without_a_row_starts_at_zero(self) -> None:
        _seed_variant()
        repo = DjangoStockRepository()

        result = repo.adjust_quantity("HB-250", 4)

        assert result == StockQuantity(4)

    def test_an_oversell_is_rejected_and_leaves_the_quantity_unchanged(self) -> None:
        _seed_variant()
        repo = DjangoStockRepository()
        repo.set_quantity("HB-250", StockQuantity(2))

        with pytest.raises(InsufficientStockError):
            repo.adjust_quantity("HB-250", -3)

        assert repo.get_quantity("HB-250") == StockQuantity(2)

    def test_raises_for_an_unknown_variant(self) -> None:
        with pytest.raises(VariantNotFoundError):
            DjangoStockRepository().adjust_quantity("GHOST", 1)


class TestGetQuantity:
    def test_defaults_to_zero_without_a_row(self) -> None:
        _seed_variant()

        assert DjangoStockRepository().get_quantity("HB-250") == StockQuantity(0)
