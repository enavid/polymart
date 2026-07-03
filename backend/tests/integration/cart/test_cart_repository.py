"""Integration tests for the Django cart repository + reader adapters (real DB)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from src.domain.cart.exceptions import CartLineNotFoundError
from src.domain.cart.value_objects import CartQuantity, Money, Sku
from src.domain.catalog.entities import Product, ProductType, ProductVariant
from src.domain.catalog.value_objects import (
    ChannelPrice,
    ProductCode,
    ProductTypeCode,
)
from src.domain.catalog.value_objects import Money as CatalogMoney
from src.domain.catalog.value_objects import Sku as CatalogSku
from src.domain.channel.entities import Channel
from src.domain.channel.value_objects import ChannelSlug, Currency
from src.infrastructure.cart.models import CartLineModel, CartModel
from src.infrastructure.cart.repositories import (
    DjangoCartRepository,
    DjangoChannelReader,
    DjangoVariantPricingReader,
)
from src.infrastructure.catalog.repositories import (
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoVariantPriceRepository,
    DjangoVariantRepository,
)
from src.infrastructure.channel.repositories import DjangoChannelRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CHANNEL = "ir-main"


def _seed_channel(slug: str = _CHANNEL, currency: str = "IRR") -> None:
    DjangoChannelRepository().add(
        Channel(slug=ChannelSlug(slug), name="Iran", currency=Currency(currency))
    )


def _seed_priced_variant(sku: str = "HB-250", amount: str = "120000.00") -> None:
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
    DjangoProductRepository().add(
        Product(
            code=ProductCode("house-blend"),
            name="House Blend",
            product_type=ProductTypeCode("coffee"),
        )
    )
    DjangoVariantRepository().add(
        ProductVariant(product=ProductCode("house-blend"), sku=CatalogSku(sku), name="HB")
    )
    DjangoVariantPriceRepository().replace(
        sku,
        (
            ChannelPrice(
                channel=_CHANNEL, money=CatalogMoney(amount=Decimal(amount), currency="IRR")
            ),
        ),
    )


def _owner(phone: str = "09120000001") -> str:
    """Create a user and return their prefixed owner id (``u:<pk>``)."""
    user = get_user_model().objects.create_user(phone_number=phone, password="pw")
    return f"u:{user.pk}"


def _user_pk(owner: str) -> int:
    """The integer user pk behind a ``u:<pk>`` owner id, for direct ORM assertions."""
    return int(owner.removeprefix("u:"))


class TestCartRepository:
    def test_get_returns_an_empty_cart_when_none_exists(self) -> None:
        owner = _owner()

        cart = DjangoCartRepository().get(owner, _CHANNEL)

        assert cart.owner == owner
        assert cart.lines == []
        assert cart.id is None

    def test_apply_persists_lines_and_get_reloads_them(self) -> None:
        owner = _owner()
        repo = DjangoCartRepository()

        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(2)))
        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-500"), CartQuantity(1)))
        reloaded = repo.get(owner, _CHANNEL)

        assert [(line.sku.value, line.quantity.value) for line in reloaded.lines] == [
            ("HB-250", 2),
            ("HB-500", 1),
        ]
        assert reloaded.id is not None

    def test_apply_replaces_lines_without_leaving_stale_rows(self) -> None:
        owner = _owner()
        repo = DjangoCartRepository()
        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(2)))

        repo.apply(owner, _CHANNEL, lambda c: c.set_item(Sku("HB-250"), CartQuantity(5)))

        assert CartModel.objects.count() == 1
        assert CartLineModel.objects.filter(cart__owner_id=_user_pk(owner)).count() == 1
        assert repo.get(owner, _CHANNEL).lines[0].quantity == CartQuantity(5)

    def test_applying_twice_does_not_create_a_second_cart(self) -> None:
        owner = _owner()
        repo = DjangoCartRepository()

        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(1)))
        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-500"), CartQuantity(1)))

        assert (
            CartModel.objects.filter(owner_id=_user_pk(owner), channel_slug=_CHANNEL).count() == 1
        )

    def test_a_mutation_that_raises_writes_nothing(self) -> None:
        owner = _owner()
        repo = DjangoCartRepository()
        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(1)))

        # Removing a line the cart does not have raises; the whole apply rolls back,
        # so the existing line survives untouched.
        with pytest.raises(CartLineNotFoundError):
            repo.apply(owner, _CHANNEL, lambda c: c.remove_item(Sku("GHOST")))

        assert [line.sku.value for line in repo.get(owner, _CHANNEL).lines] == ["HB-250"]

    def test_two_owners_keep_separate_carts(self) -> None:
        owner_a = _owner()
        owner_b = _owner(phone="09120000002")
        repo = DjangoCartRepository()
        repo.apply(owner_a, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(1)))

        assert repo.get(owner_b, _CHANNEL).lines == []

    def test_str_is_informative(self) -> None:
        owner = _owner()
        repo = DjangoCartRepository()
        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(2)))

        model = CartModel.objects.get(owner_id=_user_pk(owner))
        assert str(model) == f"{_user_pk(owner)}:{_CHANNEL}"
        assert str(model.lines.first()) == f"{model.pk}:HB-250:2"


class TestGuestCartRepository:
    """A guest cart is keyed by an opaque session token instead of a user FK."""

    def test_guest_cart_round_trips_through_the_token(self) -> None:
        owner = "g:guest-token-abc"
        repo = DjangoCartRepository()

        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(3)))
        reloaded = repo.get(owner, _CHANNEL)

        assert reloaded.owner == owner
        assert [(line.sku.value, line.quantity.value) for line in reloaded.lines] == [("HB-250", 3)]
        # Persisted as a guest row: no user FK, token stored.
        model = CartModel.objects.get(guest_token="guest-token-abc")
        assert model.owner_id is None
        assert str(model) == f"guest-token-abc:{_CHANNEL}"

    def test_a_guest_and_a_user_do_not_share_a_cart(self) -> None:
        user_owner = _owner()
        guest_owner = "g:some-guest"
        repo = DjangoCartRepository()
        repo.apply(user_owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(1)))

        assert repo.get(guest_owner, _CHANNEL).lines == []

    def test_two_guests_do_not_share_a_cart(self) -> None:
        repo = DjangoCartRepository()
        repo.apply("g:guest-one", _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(1)))

        assert repo.get("g:guest-two", _CHANNEL).lines == []


class TestMergeGuestIntoUser:
    """Merging a guest's cart into a user's cart on login (real DB)."""

    def test_merges_into_an_empty_user_cart_and_deletes_the_guest_cart(self) -> None:
        user_owner = _owner()
        guest_owner = "g:merge-token"
        repo = DjangoCartRepository()
        repo.apply(guest_owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(2)))

        merged = repo.merge_guest_into_user(guest_owner, user_owner)

        assert merged == 1
        assert [
            (line.sku.value, line.quantity.value) for line in repo.get(user_owner, _CHANNEL).lines
        ] == [("HB-250", 2)]
        # The guest cart row is gone, not orphaned.
        assert not CartModel.objects.filter(guest_token="merge-token").exists()

    def test_sums_a_shared_variant_into_an_existing_user_cart(self) -> None:
        user_owner = _owner()
        guest_owner = "g:merge-token"
        repo = DjangoCartRepository()
        repo.apply(user_owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(3)))
        repo.apply(guest_owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(4)))
        repo.apply(guest_owner, _CHANNEL, lambda c: c.add_item(Sku("HB-500"), CartQuantity(1)))

        repo.merge_guest_into_user(guest_owner, user_owner)

        assert [
            (line.sku.value, line.quantity.value) for line in repo.get(user_owner, _CHANNEL).lines
        ] == [
            ("HB-250", 7),
            ("HB-500", 1),
        ]
        assert CartLineModel.objects.filter(cart__owner_id=_user_pk(user_owner)).count() == 2

    def test_merges_every_channel_the_guest_has_a_cart_in(self) -> None:
        _seed_channel("ir-other")
        user_owner = _owner()
        guest_owner = "g:merge-token"
        repo = DjangoCartRepository()
        repo.apply(guest_owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(1)))
        repo.apply(guest_owner, "ir-other", lambda c: c.add_item(Sku("HB-500"), CartQuantity(2)))

        merged = repo.merge_guest_into_user(guest_owner, user_owner)

        assert merged == 2
        assert repo.get(user_owner, _CHANNEL).lines[0].sku.value == "HB-250"
        assert repo.get(user_owner, "ir-other").lines[0].sku.value == "HB-500"
        assert not CartModel.objects.filter(guest_token="merge-token").exists()

    def test_a_guest_with_no_cart_is_a_no_op(self) -> None:
        user_owner = _owner()
        repo = DjangoCartRepository()

        assert repo.merge_guest_into_user("g:nothing", user_owner) == 0
        assert repo.get(user_owner, _CHANNEL).lines == []

    def test_is_idempotent_when_called_twice(self) -> None:
        user_owner = _owner()
        guest_owner = "g:merge-token"
        repo = DjangoCartRepository()
        repo.apply(guest_owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(2)))

        repo.merge_guest_into_user(guest_owner, user_owner)
        second = repo.merge_guest_into_user(guest_owner, user_owner)

        assert second == 0
        assert repo.get(user_owner, _CHANNEL).lines[0].quantity == CartQuantity(2)


class TestVariantPricingReader:
    def test_exists_reflects_the_catalog(self) -> None:
        _seed_priced_variant()
        reader = DjangoVariantPricingReader()

        assert reader.exists("HB-250") is True
        assert reader.exists("GHOST") is False

    def test_price_of_returns_the_channel_price_as_money(self) -> None:
        _seed_channel()
        _seed_priced_variant(amount="120000.00")
        reader = DjangoVariantPricingReader()

        price = reader.price_of("HB-250", _CHANNEL)

        assert price == Money(amount=Decimal("120000.00"), currency="IRR")

    def test_price_of_is_none_without_a_price_in_that_channel(self) -> None:
        _seed_priced_variant()
        reader = DjangoVariantPricingReader()

        assert reader.price_of("HB-250", "other-channel") is None


class TestChannelReader:
    def test_currency_of_returns_the_channel_currency(self) -> None:
        _seed_channel(currency="IRR")

        assert DjangoChannelReader().currency_of(_CHANNEL) == "IRR"

    def test_currency_of_is_none_for_an_unknown_channel(self) -> None:
        assert DjangoChannelReader().currency_of("nope") is None
