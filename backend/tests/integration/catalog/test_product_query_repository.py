"""Integration tests for the Django product query repository (real DB)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.application.catalog.ports import ProductFilters
from src.domain.catalog.entities import (
    Category,
    Collection,
    Product,
    ProductType,
    ProductVariant,
)
from src.domain.catalog.exceptions import ProductNotFoundError
from src.domain.catalog.value_objects import (
    CategorySlug,
    ChannelPrice,
    CollectionSlug,
    MediaAsset,
    Money,
    ProductCode,
    ProductTypeCode,
    Sku,
    StockQuantity,
)
from src.infrastructure.catalog.repositories import (
    DjangoCategoryRepository,
    DjangoCollectionProductRepository,
    DjangoCollectionRepository,
    DjangoProductCategoryRepository,
    DjangoProductQueryRepository,
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoStockRepository,
    DjangoVariantPriceRepository,
    DjangoVariantRepository,
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


class TestPriceSummaries:
    @staticmethod
    def _seed_priced() -> None:
        types = DjangoProductTypeRepository()
        types.add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
        products = DjangoProductRepository()
        coffee = ProductTypeCode("coffee")
        products.add(
            Product(code=ProductCode("house-blend"), name="House Blend", product_type=coffee)
        )
        products.add(
            Product(code=ProductCode("dark-roast"), name="Dark Roast", product_type=coffee)
        )

        variants = DjangoVariantRepository()
        prices = DjangoVariantPriceRepository()
        stock = DjangoStockRepository()

        # house-blend: two variants in ir-main (120k in stock, 200k) + one only in
        # another channel -> from_price is the 120k, and it is available.
        for sku, name in (("HB-250", "250g"), ("HB-500", "500g"), ("HB-1000", "1kg")):
            variants.add(
                ProductVariant(product=ProductCode("house-blend"), sku=Sku(sku), name=name)
            )
        prices.replace(
            "HB-250", (ChannelPrice(channel="ir-main", money=Money(Decimal("120000.00"), "IRR")),)
        )
        prices.replace(
            "HB-500", (ChannelPrice(channel="ir-main", money=Money(Decimal("200000.00"), "IRR")),)
        )
        prices.replace(
            "HB-1000",
            (ChannelPrice(channel="ir-secondary", money=Money(Decimal("360000.00"), "IRR")),),
        )
        stock.set_quantity("HB-250", StockQuantity(30))
        stock.set_quantity("HB-500", StockQuantity(10))
        stock.set_quantity("HB-1000", StockQuantity(8))

        # dark-roast: priced in ir-main but out of stock -> priced, not available.
        variants.add(
            ProductVariant(product=ProductCode("dark-roast"), sku=Sku("DR-250"), name="250g")
        )
        prices.replace(
            "DR-250", (ChannelPrice(channel="ir-main", money=Money(Decimal("150000.00"), "IRR")),)
        )
        stock.set_quantity("DR-250", StockQuantity(0))

    def test_from_price_is_the_lowest_in_channel_variant_price(self) -> None:
        self._seed_priced()

        summaries = DjangoProductQueryRepository().price_summaries(
            codes=["house-blend", "dark-roast"], channel="ir-main"
        )

        assert summaries["house-blend"].from_price is not None
        assert summaries["house-blend"].from_price.amount == Decimal("120000.00")
        assert summaries["house-blend"].from_price.currency == "IRR"
        assert summaries["house-blend"].available is True

    def test_priced_but_out_of_stock_is_not_available(self) -> None:
        self._seed_priced()

        summaries = DjangoProductQueryRepository().price_summaries(
            codes=["dark-roast"], channel="ir-main"
        )

        assert summaries["dark-roast"].from_price.amount == Decimal("150000.00")
        assert summaries["dark-roast"].available is False

    def test_unpriced_in_channel_has_no_from_price(self) -> None:
        self._seed_priced()

        # Only HB-1000 is priced in ir-secondary; the others are not.
        summaries = DjangoProductQueryRepository().price_summaries(
            codes=["dark-roast"], channel="ir-secondary"
        )

        assert summaries["dark-roast"].from_price is None
        assert summaries["dark-roast"].available is False

    def test_no_codes_returns_empty(self) -> None:
        assert DjangoProductQueryRepository().price_summaries(codes=[], channel="ir-main") == {}


class TestPriceRangeFilter:
    @staticmethod
    def _seed_priced_range() -> None:
        types = DjangoProductTypeRepository()
        types.add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
        products = DjangoProductRepository()
        coffee = ProductTypeCode("coffee")
        variants = DjangoVariantRepository()
        prices = DjangoVariantPriceRepository()

        # Three products priced in ir-main at 100k / 200k / 300k, plus a "cheap"
        # product whose *lowest* variant is 100k but which also has a 900k variant
        # (proves the range filters on the from-price, not any variant), plus an
        # unpriced-in-channel product. All published.
        for code, name in (
            ("p-low", "Low"),
            ("p-mid", "Mid"),
            ("p-high", "High"),
            ("p-cheap", "Cheap"),
            ("p-unpriced", "Unpriced"),
        ):
            products.add(Product(code=ProductCode(code), name=name, product_type=coffee))
            products.set_published(code, True)

        pricing = {
            "p-low": [("LOW-1", Decimal("100000.00"))],
            "p-mid": [("MID-1", Decimal("200000.00"))],
            "p-high": [("HIGH-1", Decimal("300000.00"))],
            "p-cheap": [("CHEAP-1", Decimal("100000.00")), ("CHEAP-2", Decimal("900000.00"))],
        }
        for code, lines in pricing.items():
            for sku, amount in lines:
                variants.add(ProductVariant(product=ProductCode(code), sku=Sku(sku), name=sku))
                prices.replace(sku, (ChannelPrice(channel="ir-main", money=Money(amount, "IRR")),))
        # p-unpriced has a variant but no price in ir-main.
        variants.add(
            ProductVariant(product=ProductCode("p-unpriced"), sku=Sku("UP-1"), name="UP-1")
        )

    @staticmethod
    def _codes(**kwargs: object) -> set[str]:
        page = DjangoProductQueryRepository().search(
            filters=_filters(channel="ir-main", **kwargs), limit=50, offset=0
        )
        return {product.code.value for product in page.items}

    def test_min_price_excludes_cheaper_products(self) -> None:
        self._seed_priced_range()
        # from-price >= 150k -> p-mid (200k), p-high (300k). p-low/p-cheap (100k) and
        # p-unpriced (no in-channel price) are excluded.
        assert self._codes(min_price=Decimal("150000.00")) == {"p-mid", "p-high"}

    def test_max_price_excludes_pricier_products(self) -> None:
        self._seed_priced_range()
        # from-price <= 250k -> p-low, p-cheap (both 100k), p-mid (200k).
        assert self._codes(max_price=Decimal("250000.00")) == {"p-low", "p-cheap", "p-mid"}

    def test_min_and_max_bound_a_window(self) -> None:
        self._seed_priced_range()
        assert self._codes(min_price=Decimal("150000.00"), max_price=Decimal("250000.00")) == {
            "p-mid"
        }

    def test_filters_on_the_lowest_variant_price_not_any_variant(self) -> None:
        self._seed_priced_range()
        # p-cheap's lowest variant is 100k (its 900k variant must not pull it into a
        # high bucket, nor keep it out of a low one).
        assert "p-cheap" in self._codes(max_price=Decimal("120000.00"))
        assert "p-cheap" not in self._codes(min_price=Decimal("150000.00"))

    def test_range_without_a_channel_does_not_filter(self) -> None:
        self._seed_priced_range()
        # No channel -> price bounds are ignored; every published product is returned.
        page = DjangoProductQueryRepository().search(
            filters=_filters(min_price=Decimal("150000.00")), limit=50, offset=0
        )
        assert {p.code.value for p in page.items} == {
            "p-low",
            "p-mid",
            "p-high",
            "p-cheap",
            "p-unpriced",
        }


class TestPrimaryImages:
    @staticmethod
    def _seed_with_media() -> None:
        types = DjangoProductTypeRepository()
        types.add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
        products = DjangoProductRepository()
        coffee = ProductTypeCode("coffee")
        products.add(
            Product(code=ProductCode("house-blend"), name="House Blend", product_type=coffee)
        )
        # A product whose variants carry no media at all.
        products.add(
            Product(code=ProductCode("dark-roast"), name="Dark Roast", product_type=coffee)
        )

        variants = DjangoVariantRepository()
        # The earliest variant by SKU (HB-250) carries two images; its first (lowest
        # position) is the product's primary image. A later variant's image must not win.
        variants.add(
            ProductVariant(
                product=ProductCode("house-blend"),
                sku=Sku("HB-250"),
                name="250g",
                media=(
                    MediaAsset(url="https://cdn.example.com/hb-front.jpg", alt_text="front"),
                    MediaAsset(url="https://cdn.example.com/hb-back.jpg", alt_text="back"),
                ),
            )
        )
        variants.add(
            ProductVariant(
                product=ProductCode("house-blend"),
                sku=Sku("HB-500"),
                name="500g",
                media=(MediaAsset(url="https://cdn.example.com/hb-500.jpg", alt_text="500g"),),
            )
        )
        variants.add(
            ProductVariant(product=ProductCode("dark-roast"), sku=Sku("DR-250"), name="250g")
        )

    def test_returns_the_first_variants_first_media_asset(self) -> None:
        self._seed_with_media()

        images = DjangoProductQueryRepository().primary_images(codes=["house-blend", "dark-roast"])

        assert images["house-blend"].url == "https://cdn.example.com/hb-front.jpg"
        assert images["house-blend"].alt_text == "front"

    def test_a_product_without_variant_media_is_absent(self) -> None:
        self._seed_with_media()

        images = DjangoProductQueryRepository().primary_images(codes=["house-blend", "dark-roast"])

        assert "dark-roast" not in images

    def test_no_codes_returns_empty(self) -> None:
        assert DjangoProductQueryRepository().primary_images(codes=[]) == {}
