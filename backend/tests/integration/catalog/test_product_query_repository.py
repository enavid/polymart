"""Integration tests for the Django product query repository (real DB)."""

from __future__ import annotations

import pytest

from src.application.catalog.ports import ProductFilters
from src.domain.catalog.entities import Category, Collection, Product, ProductType
from src.domain.catalog.exceptions import ProductNotFoundError
from src.domain.catalog.value_objects import (
    CategorySlug,
    CollectionSlug,
    ProductCode,
    ProductTypeCode,
)
from src.infrastructure.catalog.repositories import (
    DjangoCategoryRepository,
    DjangoCollectionProductRepository,
    DjangoCollectionRepository,
    DjangoProductCategoryRepository,
    DjangoProductQueryRepository,
    DjangoProductRepository,
    DjangoProductTypeRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed_catalog() -> None:
    types = DjangoProductTypeRepository()
    types.add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
    types.add(ProductType(code=ProductTypeCode("tea"), name="Tea"))

    products = DjangoProductRepository()
    coffee = ProductTypeCode("coffee")
    tea = ProductTypeCode("tea")
    products.add(Product(code=ProductCode("house-blend"), name="House Blend", product_type=coffee))
    products.add(Product(code=ProductCode("espresso"), name="Espresso Roast", product_type=coffee))
    products.add(Product(code=ProductCode("green-tea"), name="Green Tea", product_type=tea))
    # Publish two of the three coffees; leave green-tea a draft.
    products.set_published("house-blend", True)
    products.set_published("espresso", True)

    categories = DjangoCategoryRepository()
    categories.add(Category(slug=CategorySlug("beverages"), name="Beverages"))
    DjangoProductCategoryRepository().replace("house-blend", (CategorySlug("beverages"),))

    collections = DjangoCollectionRepository()
    collections.add(Collection(slug=CollectionSlug("featured"), name="Featured"))
    DjangoCollectionProductRepository().replace("featured", (ProductCode("espresso"),))


def _filters(**kwargs: object) -> ProductFilters:
    base: dict[str, object] = {
        "search": None,
        "category": None,
        "collection": None,
        "product_type": None,
        "published_only": True,
    }
    base.update(kwargs)
    return ProductFilters(**base)  # type: ignore[arg-type]


class TestSearch:
    def test_published_only_excludes_drafts(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        page = repo.search(filters=_filters(), limit=20, offset=0)

        codes = [p.code.value for p in page.items]
        assert "green-tea" not in codes
        assert set(codes) == {"house-blend", "espresso"}
        assert page.total == 2

    def test_unpublished_are_visible_when_not_restricted(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        page = repo.search(filters=_filters(published_only=False), limit=20, offset=0)

        assert page.total == 3

    def test_filters_by_product_type(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        page = repo.search(filters=_filters(product_type="coffee"), limit=20, offset=0)

        assert {p.code.value for p in page.items} == {"house-blend", "espresso"}

    def test_filters_by_category(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        page = repo.search(filters=_filters(category="beverages"), limit=20, offset=0)

        assert [p.code.value for p in page.items] == ["house-blend"]

    def test_filters_by_collection(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        page = repo.search(filters=_filters(collection="featured"), limit=20, offset=0)

        assert [p.code.value for p in page.items] == ["espresso"]

    def test_search_matches_name_case_insensitively(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        page = repo.search(filters=_filters(search="espresso"), limit=20, offset=0)

        assert [p.code.value for p in page.items] == ["espresso"]

    def test_search_matches_code(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        page = repo.search(filters=_filters(search="house-blend"), limit=20, offset=0)

        assert [p.code.value for p in page.items] == ["house-blend"]

    def test_filters_combine_with_and(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        # coffee AND collection=featured -> only espresso (house-blend is not in it).
        page = repo.search(
            filters=_filters(product_type="coffee", collection="featured"), limit=20, offset=0
        )

        assert [p.code.value for p in page.items] == ["espresso"]

    def test_an_unmatched_filter_returns_an_empty_page(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        page = repo.search(filters=_filters(category="nonexistent"), limit=20, offset=0)

        assert page.items == () and page.total == 0

    def test_pagination_windows_the_results_but_counts_all(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        page = repo.search(filters=_filters(), limit=1, offset=1)

        assert len(page.items) == 1
        # total reflects every match, not just the returned window.
        assert page.total == 2

    def test_results_are_ordered_by_code(self) -> None:
        _seed_catalog()
        repo = DjangoProductQueryRepository()

        page = repo.search(filters=_filters(), limit=20, offset=0)

        assert [p.code.value for p in page.items] == ["espresso", "house-blend"]


class TestGetPublishedByCode:
    def test_returns_a_published_product(self) -> None:
        _seed_catalog()

        product = DjangoProductQueryRepository().get_published_by_code("house-blend")

        assert product.code.value == "house-blend"

    def test_a_draft_is_not_found(self) -> None:
        _seed_catalog()

        with pytest.raises(ProductNotFoundError):
            DjangoProductQueryRepository().get_published_by_code("green-tea")

    def test_an_unknown_product_is_not_found(self) -> None:
        with pytest.raises(ProductNotFoundError):
            DjangoProductQueryRepository().get_published_by_code("ghost")
