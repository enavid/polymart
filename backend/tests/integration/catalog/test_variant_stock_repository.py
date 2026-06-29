"""Integration tests for the Django variant-stock repository (real DB)."""

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
from src.infrastructure.catalog.models import VariantStockModel
from src.infrastructure.catalog.repositories import (
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoStockRepository,
    DjangoVariantRepository,
)

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
        assert VariantStockModel.objects.get(variant__sku="HB-250").quantity == 12

    def test_setting_again_overwrites_without_a_second_row(self) -> None:
        _seed_variant()
        repo = DjangoStockRepository()
        repo.set_quantity("HB-250", StockQuantity(12))

        repo.set_quantity("HB-250", StockQuantity(3))

        assert VariantStockModel.objects.filter(variant__sku="HB-250").count() == 1
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


def test_variant_stock_model_str_is_informative() -> None:
    _seed_variant()
    DjangoStockRepository().set_quantity("HB-250", StockQuantity(7))

    stock = VariantStockModel.objects.get(variant__sku="HB-250")
    assert str(stock) == f"{stock.variant_id}:7"
