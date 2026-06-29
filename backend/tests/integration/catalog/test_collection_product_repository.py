"""Integration tests for the Django collection-membership repository (real DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Collection, Product, ProductType
from src.domain.catalog.exceptions import CollectionNotFoundError, UnknownProductError
from src.domain.catalog.value_objects import (
    CollectionSlug,
    ProductCode,
    ProductTypeCode,
)
from src.infrastructure.catalog.models import CollectionProductModel
from src.infrastructure.catalog.repositories import (
    DjangoCollectionProductRepository,
    DjangoCollectionRepository,
    DjangoProductRepository,
    DjangoProductTypeRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed_collection(slug: str = "featured") -> None:
    DjangoCollectionRepository().add(Collection(slug=CollectionSlug(slug), name=slug.title()))


def _seed_products(*codes: str) -> None:
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
    repo = DjangoProductRepository()
    for code in codes:
        repo.add(
            Product(
                code=ProductCode(code), name=code.title(), product_type=ProductTypeCode("coffee")
            )
        )


def _codes(*values: str) -> tuple[ProductCode, ...]:
    return tuple(ProductCode(value) for value in values)


class TestReplace:
    def test_assigns_products_in_order(self) -> None:
        _seed_collection()
        _seed_products("house-blend", "cold-brew")
        repo = DjangoCollectionProductRepository()

        result = repo.replace("featured", _codes("cold-brew", "house-blend"))

        assert [p.value for p in result] == ["cold-brew", "house-blend"]

    def test_replacing_overwrites_the_previous_membership(self) -> None:
        _seed_collection()
        _seed_products("house-blend", "cold-brew", "espresso-shot")
        repo = DjangoCollectionProductRepository()
        repo.replace("featured", _codes("house-blend", "cold-brew"))

        result = repo.replace("featured", _codes("espresso-shot"))

        assert [p.value for p in result] == ["espresso-shot"]
        assert CollectionProductModel.objects.filter(collection__slug="featured").count() == 1

    def test_replacing_with_an_empty_list_clears_membership(self) -> None:
        _seed_collection()
        _seed_products("house-blend")
        repo = DjangoCollectionProductRepository()
        repo.replace("featured", _codes("house-blend"))

        result = repo.replace("featured", ())

        assert result == ()
        assert not CollectionProductModel.objects.filter(collection__slug="featured").exists()

    def test_raises_if_the_collection_vanished(self) -> None:
        with pytest.raises(CollectionNotFoundError):
            DjangoCollectionProductRepository().replace("ghost", _codes("house-blend"))

    def test_raises_and_rolls_back_if_a_product_vanished(self) -> None:
        # Defends the use case's check-then-act window: a product was validated, then
        # deleted before this replace ran. The whole replace must roll back.
        _seed_collection()
        _seed_products("house-blend")
        repo = DjangoCollectionProductRepository()
        repo.replace("featured", _codes("house-blend"))

        with pytest.raises(UnknownProductError):
            repo.replace("featured", _codes("ghost"))

        # The prior membership is untouched (the delete was rolled back).
        assert [p.value for p in repo.list_for_collection("featured")] == ["house-blend"]


class TestListForCollection:
    def test_returns_membership_in_assignment_order(self) -> None:
        _seed_collection()
        _seed_products("house-blend", "cold-brew")
        repo = DjangoCollectionProductRepository()
        repo.replace("featured", _codes("cold-brew", "house-blend"))

        result = repo.list_for_collection("featured")

        assert [p.value for p in result] == ["cold-brew", "house-blend"]

    def test_returns_empty_for_a_collection_without_products(self) -> None:
        _seed_collection()

        assert DjangoCollectionProductRepository().list_for_collection("featured") == ()


def test_collection_product_model_str_is_informative() -> None:
    _seed_collection()
    _seed_products("house-blend")
    DjangoCollectionProductRepository().replace("featured", _codes("house-blend"))

    link = CollectionProductModel.objects.get(collection__slug="featured")
    assert str(link) == f"{link.collection_id}:{link.product_id}"
