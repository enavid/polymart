"""Integration tests for the Django variant repository (real DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Product, ProductType, ProductVariant
from src.domain.catalog.exceptions import (
    ProductNotFoundError,
    VariantAlreadyExistsError,
    VariantNotFoundError,
)
from src.domain.catalog.value_objects import ProductCode, ProductTypeCode, Sku
from src.infrastructure.catalog.models import ProductVariantModel
from src.infrastructure.catalog.repositories import (
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoVariantRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed_product(code: str = "house-blend") -> None:
    """Create a 'coffee' product type and a product to attach variants to."""
    DjangoProductTypeRepository().add(
        ProductType(code=ProductTypeCode("coffee"), name="Coffee")
    )
    DjangoProductRepository().add(
        Product(
            code=ProductCode(code),
            name=code.title(),
            product_type=ProductTypeCode("coffee"),
        )
    )


def _variant(product: str, sku: str, name: str) -> ProductVariant:
    return ProductVariant(product=ProductCode(product), sku=Sku(sku), name=name)


class TestAdd:
    def test_persists_a_variant(self) -> None:
        _seed_product()
        repo = DjangoVariantRepository()

        stored = repo.add(_variant("house-blend", "coffee-250", "250g Bag"))

        assert stored.id is not None
        assert stored.sku.value == "COFFEE-250"
        assert stored.product.value == "house-blend"
        assert ProductVariantModel.objects.filter(sku="COFFEE-250").exists()

    def test_rejects_a_duplicate_sku(self) -> None:
        _seed_product()
        repo = DjangoVariantRepository()
        repo.add(_variant("house-blend", "coffee-250", "250g Bag"))

        with pytest.raises(VariantAlreadyExistsError):
            repo.add(_variant("house-blend", "coffee-250", "Another"))

    def test_rejects_a_variant_for_an_unknown_product(self) -> None:
        # Defensive guard: the use case resolves the product; this exercises the
        # repository path where it has vanished (concurrent-deletion race).
        with pytest.raises(ProductNotFoundError):
            DjangoVariantRepository().add(_variant("ghost", "coffee-250", "250g Bag"))

        assert ProductVariantModel.objects.filter(sku="COFFEE-250").exists() is False


class TestReads:
    def test_get_by_sku_round_trips_the_entity(self) -> None:
        _seed_product()
        repo = DjangoVariantRepository()
        repo.add(_variant("house-blend", "coffee-250", "250g Bag"))

        loaded = repo.get_by_sku("COFFEE-250")

        assert loaded.name == "250g Bag"
        assert loaded.product.value == "house-blend"

    def test_get_by_sku_raises_when_missing(self) -> None:
        with pytest.raises(VariantNotFoundError):
            DjangoVariantRepository().get_by_sku("GHOST")

    def test_exists_by_sku_reflects_persistence(self) -> None:
        _seed_product()
        repo = DjangoVariantRepository()
        assert repo.exists_by_sku("COFFEE-250") is False

        repo.add(_variant("house-blend", "coffee-250", "250g Bag"))
        assert repo.exists_by_sku("COFFEE-250") is True

    def test_list_for_product_returns_only_that_products_variants_sorted(self) -> None:
        _seed_product("house-blend")
        _other_product("tea-blend")
        repo = DjangoVariantRepository()
        repo.add(_variant("house-blend", "coffee-1000", "1kg Bag"))
        repo.add(_variant("house-blend", "coffee-250", "250g Bag"))
        repo.add(_variant("tea-blend", "tea-100", "100g Tin"))

        listed = repo.list_for_product("house-blend")

        assert [v.sku.value for v in listed] == ["COFFEE-1000", "COFFEE-250"]


def _other_product(code: str) -> None:
    DjangoProductRepository().add(
        Product(code=ProductCode(code), name=code.title(), product_type=ProductTypeCode("coffee"))
    )


def test_variant_model_str_is_the_sku() -> None:
    _seed_product()
    DjangoVariantRepository().add(_variant("house-blend", "coffee-250", "250g Bag"))

    assert str(ProductVariantModel.objects.get(sku="COFFEE-250")) == "COFFEE-250"
