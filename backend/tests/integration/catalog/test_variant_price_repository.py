"""Integration tests for the Django variant-price repository + channel reader (real DB)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.catalog.entities import Product, ProductType, ProductVariant
from src.domain.catalog.exceptions import VariantNotFoundError
from src.domain.catalog.value_objects import (
    ChannelPrice,
    Money,
    ProductCode,
    ProductTypeCode,
    Sku,
)
from src.domain.channel.entities import Channel
from src.domain.channel.value_objects import ChannelSlug, Currency
from src.infrastructure.catalog.models import VariantPriceModel
from src.infrastructure.catalog.repositories import (
    DjangoChannelReader,
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoVariantPriceRepository,
    DjangoVariantRepository,
)
from src.infrastructure.channel.repositories import DjangoChannelRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed_variant(sku: str = "HB-250") -> None:
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
    DjangoProductRepository().add(
        Product(
            code=ProductCode("house-blend"),
            name="House Blend",
            product_type=ProductTypeCode("coffee"),
        )
    )
    DjangoVariantRepository().add(
        ProductVariant(product=ProductCode("house-blend"), sku=Sku(sku), name="House Blend 250g")
    )


def _price(channel: str, amount: str, currency: str = "IRR") -> ChannelPrice:
    return ChannelPrice(channel=channel, money=Money(amount=Decimal(amount), currency=currency))


class TestReplace:
    def test_stores_prices_ordered_by_channel(self) -> None:
        _seed_variant()
        repo = DjangoVariantPriceRepository()

        result = repo.replace(
            "HB-250",
            (_price("us-store", "9.99", "USD"), _price("ir-toman", "1500", "IRR")),
        )

        assert [(p.channel, p.money.currency) for p in result] == [
            ("ir-toman", "IRR"),
            ("us-store", "USD"),
        ]

    def test_stores_the_decimal_amount_exactly(self) -> None:
        _seed_variant()
        repo = DjangoVariantPriceRepository()

        result = repo.replace("HB-250", (_price("ir-toman", "1500.50"),))

        amount = result[0].money.amount
        assert isinstance(amount, Decimal)
        assert amount == Decimal("1500.50")

    def test_replacing_overwrites_the_previous_prices(self) -> None:
        _seed_variant()
        repo = DjangoVariantPriceRepository()
        repo.replace("HB-250", (_price("ir-toman", "1500"),))

        result = repo.replace("HB-250", (_price("us-store", "9.99", "USD"),))

        assert [p.channel for p in result] == ["us-store"]
        assert VariantPriceModel.objects.filter(variant__sku="HB-250").count() == 1

    def test_replacing_with_an_empty_set_clears_it(self) -> None:
        _seed_variant()
        repo = DjangoVariantPriceRepository()
        repo.replace("HB-250", (_price("ir-toman", "1500"),))

        result = repo.replace("HB-250", ())

        assert result == ()
        assert not VariantPriceModel.objects.filter(variant__sku="HB-250").exists()

    def test_raises_if_the_variant_vanished(self) -> None:
        with pytest.raises(VariantNotFoundError):
            DjangoVariantPriceRepository().replace("GHOST", (_price("ir-toman", "1500"),))


class TestListForVariant:
    def test_returns_prices_ordered_by_channel(self) -> None:
        _seed_variant()
        repo = DjangoVariantPriceRepository()
        repo.replace(
            "HB-250",
            (_price("us-store", "9.99", "USD"), _price("ir-toman", "1500", "IRR")),
        )

        result = repo.list_for_variant("HB-250")

        assert [p.channel for p in result] == ["ir-toman", "us-store"]

    def test_returns_empty_for_a_variant_without_prices(self) -> None:
        _seed_variant()

        assert DjangoVariantPriceRepository().list_for_variant("HB-250") == ()


class TestChannelReader:
    def test_returns_the_currency_of_an_existing_channel(self) -> None:
        DjangoChannelRepository().add(
            Channel(slug=ChannelSlug("ir-toman"), name="Iran", currency=Currency("IRR"))
        )

        assert DjangoChannelReader().currency_of("ir-toman") == "IRR"

    def test_returns_none_for_an_unknown_channel(self) -> None:
        assert DjangoChannelReader().currency_of("ghost") is None


def test_variant_price_model_str_is_informative() -> None:
    _seed_variant()
    DjangoVariantPriceRepository().replace("HB-250", (_price("ir-toman", "1500"),))

    price = VariantPriceModel.objects.get(variant__sku="HB-250")
    assert str(price) == f"{price.variant_id}:ir-toman:1500.0000 IRR"
