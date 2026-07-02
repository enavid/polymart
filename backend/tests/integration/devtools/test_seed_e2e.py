"""Integration tests for the ``seed_e2e`` management command (real DB).

The command underpins the Playwright suite, so it must be dependable: it writes a
known dataset, is safe to re-run (idempotent), and refuses to touch a non-DEBUG
(production-like) database.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from src.domain.access.registry import (
    ACCESS_ADMIN_ROLE,
    CATALOG_ADMIN_ROLE,
    CHANNEL_ADMIN_ROLE,
)
from src.infrastructure.cart.models import CartLineModel, CartModel
from src.infrastructure.catalog.models import (
    CategoryModel,
    CollectionModel,
    CollectionProductModel,
    ProductModel,
    ProductVariantModel,
    VariantPriceModel,
    VariantStockModel,
)
from src.infrastructure.channel.models import ChannelModel
from src.infrastructure.devtools.management.commands.seed_e2e import (
    CHANNEL_SLUG,
    COLLECTION_SLUG,
    PRODUCTS,
    SHOPPER_PHONE,
    STAFF_PHONE,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_SHOPPER_CANONICAL = "+989120000001"
_STAFF_CANONICAL = "+989120000009"


def _seed() -> None:
    with override_settings(DEBUG=True):
        call_command("seed_e2e")


class TestSeedGuard:
    def test_refuses_to_run_outside_debug(self) -> None:
        with override_settings(DEBUG=False), pytest.raises(CommandError):
            call_command("seed_e2e")


class TestSeedUsers:
    def test_creates_shopper_and_staff_with_canonical_phones(self) -> None:
        _seed()
        users = get_user_model().objects

        shopper = users.get(phone_number=_SHOPPER_CANONICAL)
        staff = users.get(phone_number=_STAFF_CANONICAL)
        assert shopper.check_password("shopper-pass-123")
        assert staff.check_password("staff-pass-123")
        assert staff.is_staff is True

    def test_staff_holds_every_admin_role(self) -> None:
        _seed()
        staff = get_user_model().objects.get(phone_number=_STAFF_CANONICAL)

        groups = set(staff.groups.values_list("name", flat=True))
        assert {CATALOG_ADMIN_ROLE, ACCESS_ADMIN_ROLE, CHANNEL_ADMIN_ROLE} <= groups

    def test_login_lookup_matches_the_raw_phone_the_command_was_given(self) -> None:
        # Regression guard: the command must store the phone in the canonical form
        # login normalises to, or a second run (and every login) would miss.
        _seed()
        assert get_user_model().objects.filter(phone_number=_SHOPPER_CANONICAL).exists()
        assert not get_user_model().objects.filter(phone_number=SHOPPER_PHONE).exists()
        assert STAFF_PHONE  # imported constant is the raw input, kept for the FE mirror


class TestSeedCatalog:
    def test_seeds_channel_products_variants_prices_and_stock(self) -> None:
        _seed()

        assert ChannelModel.objects.filter(slug=CHANNEL_SLUG).exists()
        assert ProductModel.objects.filter(is_published=True).count() == len(PRODUCTS)

        variant_count = sum(len(product.variants) for product in PRODUCTS)
        assert ProductVariantModel.objects.count() == variant_count
        assert VariantPriceModel.objects.count() == variant_count
        assert VariantStockModel.objects.count() == variant_count

        hb_250 = VariantPriceModel.objects.get(variant__sku="HB-250")
        assert hb_250.amount == Decimal("120000.00")

    def test_seeds_a_product_description_for_the_storefront_pdp(self) -> None:
        _seed()

        house_blend = ProductModel.objects.get(code="house-blend")
        assert house_blend.metadata["description"]

    def test_seeds_the_category_tree_and_a_collection_with_members(self) -> None:
        _seed()

        assert CategoryModel.objects.filter(slug="coffee-beans", parent__slug="hot-drinks").exists()
        assert CollectionModel.objects.filter(slug=COLLECTION_SLUG).exists()
        # The first two products are the seeded "featured" members.
        assert CollectionProductModel.objects.filter(collection__slug=COLLECTION_SLUG).count() == 2


class TestSeedIsIdempotent:
    def test_running_twice_leaves_the_same_data(self) -> None:
        _seed()
        _seed()

        assert get_user_model().objects.count() == 2
        assert ProductModel.objects.count() == len(PRODUCTS)
        assert ProductVariantModel.objects.count() == sum(len(p.variants) for p in PRODUCTS)
        assert VariantPriceModel.objects.count() == sum(len(p.variants) for p in PRODUCTS)
        assert ChannelModel.objects.filter(slug=CHANNEL_SLUG).count() == 1
        assert CollectionProductModel.objects.filter(collection__slug=COLLECTION_SLUG).count() == 2

    def test_clears_the_shoppers_cart_on_each_run(self) -> None:
        _seed()
        shopper = get_user_model().objects.get(phone_number=_SHOPPER_CANONICAL)
        cart = CartModel.objects.create(owner=shopper, channel_slug=CHANNEL_SLUG)
        CartLineModel.objects.create(cart=cart, sku="HB-250", quantity=1, position=0)

        _seed()

        assert CartModel.objects.filter(owner_id=shopper.pk).count() == 0
