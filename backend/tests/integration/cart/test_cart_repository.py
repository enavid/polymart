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


def _owner() -> str:
    user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
    return str(user.pk)


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
        assert CartLineModel.objects.filter(cart__owner_id=owner).count() == 1
        assert repo.get(owner, _CHANNEL).lines[0].quantity == CartQuantity(5)

    def test_applying_twice_does_not_create_a_second_cart(self) -> None:
        owner = _owner()
        repo = DjangoCartRepository()

        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(1)))
        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-500"), CartQuantity(1)))

        assert CartModel.objects.filter(owner_id=owner, channel_slug=_CHANNEL).count() == 1

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
        user_b = get_user_model().objects.create_user(phone_number="09120000002", password="pw")
        owner_b = str(user_b.pk)
        repo = DjangoCartRepository()
        repo.apply(owner_a, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(1)))

        assert repo.get(owner_b, _CHANNEL).lines == []

    def test_str_is_informative(self) -> None:
        owner = _owner()
        repo = DjangoCartRepository()
        repo.apply(owner, _CHANNEL, lambda c: c.add_item(Sku("HB-250"), CartQuantity(2)))

        model = CartModel.objects.get(owner_id=owner)
        assert str(model) == f"{owner}:{_CHANNEL}"
        assert str(model.lines.first()) == f"{model.pk}:HB-250:2"


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
