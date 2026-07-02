"""Unit tests for the storefront variant read use case (fakes, no DB)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import pytest

from src.application.catalog.ports import (
    ProductFilters,
    ProductPage,
    ProductQueryRepository,
    VariantPriceRepository,
    VariantRepository,
)
from src.application.catalog.use_cases import GetStorefrontProductVariants
from src.domain.catalog.entities import Product, ProductVariant
from src.domain.catalog.exceptions import ProductNotFoundError
from src.domain.catalog.value_objects import (
    ChannelPrice,
    Money,
    ProductCode,
    ProductTypeCode,
    Sku,
)

_CHANNEL = "ir-main"


class FakeProductQueryRepository(ProductQueryRepository):
    def __init__(self, *, published: bool) -> None:
        self._published = published

    def search(self, *, filters: ProductFilters, limit: int, offset: int) -> ProductPage:
        raise NotImplementedError  # pragma: no cover - unused here

    def price_summaries(self, *, codes, channel):  # pragma: no cover - unused here
        return {}

    def get_published_by_code(self, code: str) -> Product:
        if not self._published:
            raise ProductNotFoundError(code)
        return Product(
            code=ProductCode(code), name="House Blend", product_type=ProductTypeCode("coffee")
        )


class FakeVariantRepository(VariantRepository):
    def __init__(self, variants: list[ProductVariant]) -> None:
        self._variants = variants

    def add(self, variant: ProductVariant) -> ProductVariant:  # pragma: no cover - unused
        raise NotImplementedError

    def get_by_sku(self, sku: str) -> ProductVariant:  # pragma: no cover - unused
        raise NotImplementedError

    def exists_by_sku(self, sku: str) -> bool:  # pragma: no cover - unused
        raise NotImplementedError

    def list_for_product(self, product_code: str) -> list[ProductVariant]:
        return self._variants


class FakeVariantPriceRepository(VariantPriceRepository):
    def __init__(self, prices: dict[str, tuple[ChannelPrice, ...]]) -> None:
        self._prices = prices

    def replace(self, sku: str, prices: Sequence[ChannelPrice]) -> tuple[ChannelPrice, ...]:
        raise NotImplementedError  # pragma: no cover - unused here

    def list_for_variant(self, sku: str) -> tuple[ChannelPrice, ...]:
        return self._prices.get(sku, ())


def _variant(sku: str) -> ProductVariant:
    return ProductVariant(product=ProductCode("house-blend"), sku=Sku(sku), name=sku)


def _price(amount: str, channel: str = _CHANNEL) -> ChannelPrice:
    return ChannelPrice(channel=channel, money=Money(amount=Decimal(amount), currency="IRR"))


class TestGetStorefrontProductVariants:
    def test_returns_variants_with_their_channel_price(self) -> None:
        use_case = GetStorefrontProductVariants(
            FakeProductQueryRepository(published=True),
            FakeVariantRepository([_variant("HB-250"), _variant("HB-500")]),
            FakeVariantPriceRepository(
                {"HB-250": (_price("120000"),), "HB-500": (_price("200000"),)}
            ),
        )

        result = use_case.execute(code="house-blend", channel=_CHANNEL)

        assert [item.variant.sku.value for item in result] == ["HB-250", "HB-500"]
        assert result[0].price is not None
        assert result[0].price.money.amount == Decimal("120000")

    def test_variant_without_a_price_in_the_channel_has_none(self) -> None:
        use_case = GetStorefrontProductVariants(
            FakeProductQueryRepository(published=True),
            FakeVariantRepository([_variant("HB-250")]),
            FakeVariantPriceRepository({"HB-250": (_price("9.99", channel="other"),)}),
        )

        result = use_case.execute(code="house-blend", channel=_CHANNEL)

        assert result[0].price is None

    def test_a_draft_or_unknown_product_is_not_found(self) -> None:
        use_case = GetStorefrontProductVariants(
            FakeProductQueryRepository(published=False),
            FakeVariantRepository([]),
            FakeVariantPriceRepository({}),
        )

        with pytest.raises(ProductNotFoundError):
            use_case.execute(code="house-blend", channel=_CHANNEL)

    def test_a_product_with_no_variants_returns_empty(self) -> None:
        use_case = GetStorefrontProductVariants(
            FakeProductQueryRepository(published=True),
            FakeVariantRepository([]),
            FakeVariantPriceRepository({}),
        )

        assert use_case.execute(code="house-blend", channel=_CHANNEL) == ()
