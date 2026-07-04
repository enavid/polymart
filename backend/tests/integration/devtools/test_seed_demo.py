"""Integration tests for the ``seed_demo`` management command (real DB).

``seed_demo`` fills a local dev database with a large, varied demo catalog (many
niches, ~100 products) so the storefront and admin can be explored with realistic
data. Like ``seed_e2e`` it must be idempotent and refuse to run outside DEBUG.
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from src.infrastructure.catalog.models import (
    CategoryModel,
    CollectionModel,
    CollectionProductModel,
    ProductModel,
    ProductTypeModel,
    ProductVariantMediaModel,
    ProductVariantModel,
    VariantPriceModel,
    VariantStockModel,
)
from src.infrastructure.channel.models import ChannelModel
from src.infrastructure.devtools.management.commands.seed_demo import (
    CHANNEL_SLUG,
    NICHES,
    build_products,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed() -> None:
    with override_settings(DEBUG=True):
        call_command("seed_demo")


def _total_variants() -> int:
    return sum(len(product.variants) for product in build_products())


class TestSeedGuard:
    def test_refuses_to_run_outside_debug(self) -> None:
        with override_settings(DEBUG=False), pytest.raises(CommandError):
            call_command("seed_demo")


class TestDemoCatalogShape:
    def test_defines_at_least_a_hundred_products_across_many_niches(self) -> None:
        products = build_products()
        assert len(products) >= 100
        assert len(NICHES) >= 6
        # Product codes are unique (a duplicate would silently drop a product).
        assert len({p.code for p in products}) == len(products)
        # SKUs are unique across the whole catalog.
        skus = [v.sku for p in products for v in p.variants]
        assert len(set(skus)) == len(skus)

    def test_gives_every_product_a_stable_real_photo_url(self) -> None:
        products = build_products()
        # Every product carries a real, on-topic demo photo (not a placeholder).
        assert all(p.image_url.startswith("https://images.unsplash.com/") for p in products)
        # The URL is deterministic across builds (pinned per niche + index).
        assert {p.code: p.image_url for p in build_products()} == {
            p.code: p.image_url for p in products
        }
        # Neighbouring products in a niche never share an image (curated pools >= 5).
        for niche in NICHES:
            urls = [p.image_url for p in products if p.code.startswith(f"{niche.code}-")]
            assert all(a != b for a, b in pairwise(urls))


class TestSeedCatalog:
    def test_seeds_every_product_published_with_variants_prices_and_stock(self) -> None:
        _seed()

        assert ChannelModel.objects.filter(slug=CHANNEL_SLUG).exists()
        assert ProductModel.objects.filter(is_published=True).count() == len(build_products())
        assert ProductTypeModel.objects.count() == len(NICHES)

        total_variants = _total_variants()
        assert ProductVariantModel.objects.count() == total_variants
        assert VariantPriceModel.objects.count() == total_variants
        assert VariantStockModel.objects.count() == total_variants

        # Each product gets exactly one primary photo, attached to its first variant.
        assert ProductVariantMediaModel.objects.count() == len(build_products())

    def test_seeds_varied_data_to_exercise_the_ui(self) -> None:
        _seed()
        # At least one out-of-stock line (empty-state UI) ...
        assert VariantStockModel.objects.filter(quantity=0).exists()
        # ... and at least one multi-variant product (variant picker UI).
        multi = [p for p in build_products() if len(p.variants) > 1]
        assert multi

    def test_seeds_category_tree_and_collections_with_members(self) -> None:
        _seed()
        # Every niche contributes a root category with a child under it.
        assert CategoryModel.objects.filter(parent__isnull=False).count() >= len(NICHES)
        assert CollectionModel.objects.exists()
        assert CollectionProductModel.objects.exists()

    def test_seeds_a_storefront_description_for_every_product(self) -> None:
        _seed()
        for product in ProductModel.objects.all():
            assert product.metadata.get("description")


class TestSeedIsIdempotent:
    def test_running_twice_leaves_the_same_data(self) -> None:
        _seed()
        _seed()

        assert ProductModel.objects.count() == len(build_products())
        assert ProductVariantModel.objects.count() == _total_variants()
        assert VariantPriceModel.objects.count() == _total_variants()
        assert ChannelModel.objects.filter(slug=CHANNEL_SLUG).count() == 1
        assert ProductTypeModel.objects.count() == len(NICHES)
