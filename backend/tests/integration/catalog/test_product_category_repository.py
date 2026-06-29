"""Integration tests for the Django product-category repository (real DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Category, Product, ProductType
from src.domain.catalog.exceptions import ProductNotFoundError, UnknownCategoryError
from src.domain.catalog.value_objects import (
    CategorySlug,
    ProductCode,
    ProductTypeCode,
)
from src.infrastructure.catalog.models import ProductCategoryModel
from src.infrastructure.catalog.repositories import (
    DjangoCategoryRepository,
    DjangoProductCategoryRepository,
    DjangoProductRepository,
    DjangoProductTypeRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed_product(code: str = "house-blend") -> None:
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
    DjangoProductRepository().add(
        Product(code=ProductCode(code), name=code.title(), product_type=ProductTypeCode("coffee"))
    )


def _seed_categories(*slugs: str) -> None:
    repo = DjangoCategoryRepository()
    for slug in slugs:
        repo.add(Category(slug=CategorySlug(slug), name=slug.title()))


def _slugs(*values: str) -> tuple[CategorySlug, ...]:
    return tuple(CategorySlug(value) for value in values)


class TestReplace:
    def test_assigns_categories_in_order(self) -> None:
        _seed_product()
        _seed_categories("coffee", "espresso")
        repo = DjangoProductCategoryRepository()

        result = repo.replace("house-blend", _slugs("espresso", "coffee"))

        assert [c.value for c in result] == ["espresso", "coffee"]

    def test_replacing_overwrites_the_previous_membership(self) -> None:
        _seed_product()
        _seed_categories("coffee", "espresso", "tea")
        repo = DjangoProductCategoryRepository()
        repo.replace("house-blend", _slugs("coffee", "espresso"))

        result = repo.replace("house-blend", _slugs("tea"))

        assert [c.value for c in result] == ["tea"]
        assert ProductCategoryModel.objects.filter(product__code="house-blend").count() == 1

    def test_replacing_with_an_empty_set_clears_membership(self) -> None:
        _seed_product()
        _seed_categories("coffee")
        repo = DjangoProductCategoryRepository()
        repo.replace("house-blend", _slugs("coffee"))

        result = repo.replace("house-blend", ())

        assert result == ()
        assert not ProductCategoryModel.objects.filter(product__code="house-blend").exists()

    def test_raises_if_the_product_vanished(self) -> None:
        with pytest.raises(ProductNotFoundError):
            DjangoProductCategoryRepository().replace("ghost", _slugs("coffee"))

    def test_raises_and_rolls_back_if_a_category_vanished(self) -> None:
        # Defends the use case's check-then-act window: a category was validated,
        # then deleted before this replace ran. The whole replace must roll back.
        _seed_product()
        _seed_categories("coffee")
        repo = DjangoProductCategoryRepository()
        repo.replace("house-blend", _slugs("coffee"))

        with pytest.raises(UnknownCategoryError):
            repo.replace("house-blend", _slugs("ghost"))

        # The prior membership is untouched (the delete was rolled back).
        assert [c.value for c in repo.list_for_product("house-blend")] == ["coffee"]


class TestListForProduct:
    def test_returns_membership_in_assignment_order(self) -> None:
        _seed_product()
        _seed_categories("coffee", "espresso")
        repo = DjangoProductCategoryRepository()
        repo.replace("house-blend", _slugs("espresso", "coffee"))

        result = repo.list_for_product("house-blend")

        assert [c.value for c in result] == ["espresso", "coffee"]

    def test_returns_empty_for_a_product_without_categories(self) -> None:
        _seed_product()

        assert DjangoProductCategoryRepository().list_for_product("house-blend") == ()


def test_product_category_model_str_is_informative() -> None:
    _seed_product()
    _seed_categories("coffee")
    DjangoProductCategoryRepository().replace("house-blend", _slugs("coffee"))

    link = ProductCategoryModel.objects.get(product__code="house-blend")
    assert str(link) == f"{link.product_id}:{link.category_id}"
