"""Integration tests for the Django catalog import writer (real DB, atomicity)."""

from __future__ import annotations

import pytest

from src.application.catalog.ports import ProductImportItem
from src.domain.catalog.entities import Category, Product, ProductType
from src.domain.catalog.exceptions import ProductAlreadyExistsError
from src.domain.catalog.value_objects import (
    CategorySlug,
    ProductCode,
    ProductTypeCode,
)
from src.infrastructure.catalog.models import ProductModel
from src.infrastructure.catalog.repositories import (
    DjangoCatalogImportWriter,
    DjangoCategoryRepository,
    DjangoProductCategoryRepository,
    DjangoProductTypeRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed_catalog() -> None:
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
    DjangoCategoryRepository().add(Category(slug=CategorySlug("espresso"), name="Espresso"))


def _product(code: str) -> Product:
    return Product(
        code=ProductCode(code), name=code.title(), product_type=ProductTypeCode("coffee")
    )


def _item(code: str, *categories: str) -> ProductImportItem:
    return ProductImportItem(
        product=_product(code),
        categories=tuple(CategorySlug(slug) for slug in categories),
    )


def test_creates_products_with_and_without_categories() -> None:
    _seed_catalog()

    DjangoCatalogImportWriter().create_products(
        [_item("house-blend", "espresso"), _item("cold-brew")]
    )

    assert set(ProductModel.objects.values_list("code", flat=True)) == {"house-blend", "cold-brew"}
    categories = DjangoProductCategoryRepository().list_for_product("house-blend")
    assert [c.value for c in categories] == ["espresso"]
    assert DjangoProductCategoryRepository().list_for_product("cold-brew") == ()


def test_is_all_or_nothing_when_a_later_row_fails() -> None:
    _seed_catalog()

    # The second item duplicates the first's code: the whole batch must roll back.
    with pytest.raises(ProductAlreadyExistsError):
        DjangoCatalogImportWriter().create_products([_item("house-blend"), _item("house-blend")])

    assert ProductModel.objects.filter(code="house-blend").exists() is False
