"""Integration tests for the Django variant repository (real DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Attribute, Product, ProductType, ProductVariant
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    ProductNotFoundError,
    UnknownAttributeError,
    VariantAlreadyExistsError,
    VariantNotFoundError,
)
from src.domain.catalog.value_objects import (
    AttributeCode,
    AttributeValue,
    MediaAsset,
    ProductCode,
    ProductTypeCode,
    Sku,
)
from src.infrastructure.catalog.models import (
    ProductVariantAttributeValueModel,
    ProductVariantMediaModel,
    ProductVariantModel,
)
from src.infrastructure.catalog.repositories import (
    DjangoAttributeRepository,
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoVariantRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed_product(code: str = "house-blend", *variant_attributes: str) -> None:
    """Create a 'coffee' product type and a product to attach variants to.

    Any ``variant_attributes`` are created as plain-text attributes and assigned
    to the type at the variant level.
    """
    attributes = DjangoAttributeRepository()
    for attribute_code in variant_attributes:
        attributes.add(
            Attribute(
                code=AttributeCode(attribute_code),
                name=attribute_code.title(),
                input_type=AttributeInputType.PLAIN_TEXT,
            )
        )
    DjangoProductTypeRepository().add(
        ProductType(
            code=ProductTypeCode("coffee"),
            name="Coffee",
            variant_attributes=tuple(AttributeCode(c) for c in variant_attributes),
        )
    )
    DjangoProductRepository().add(
        Product(
            code=ProductCode(code),
            name=code.title(),
            product_type=ProductTypeCode("coffee"),
        )
    )


def _value(code: str, value: str) -> AttributeValue:
    return AttributeValue(attribute=AttributeCode(code), value=value)


def _variant(
    product: str,
    sku: str,
    name: str,
    values: tuple[AttributeValue, ...] = (),
    media: tuple[MediaAsset, ...] = (),
) -> ProductVariant:
    return ProductVariant(
        product=ProductCode(product), sku=Sku(sku), name=name, values=values, media=media
    )


class TestAdd:
    def test_persists_a_variant(self) -> None:
        _seed_product()
        repo = DjangoVariantRepository()

        stored = repo.add(_variant("house-blend", "coffee-250", "250g Bag"))

        assert stored.id is not None
        assert stored.sku.value == "COFFEE-250"
        assert stored.product.value == "house-blend"
        assert ProductVariantModel.objects.filter(sku="COFFEE-250").exists()

    def test_rejects_a_duplicate_sku(self) -> None:
        _seed_product()
        repo = DjangoVariantRepository()
        repo.add(_variant("house-blend", "coffee-250", "250g Bag"))

        with pytest.raises(VariantAlreadyExistsError):
            repo.add(_variant("house-blend", "coffee-250", "Another"))

    def test_rejects_a_variant_for_an_unknown_product(self) -> None:
        # Defensive guard: the use case resolves the product; this exercises the
        # repository path where it has vanished (concurrent-deletion race).
        with pytest.raises(ProductNotFoundError):
            DjangoVariantRepository().add(_variant("ghost", "coffee-250", "250g Bag"))

        assert ProductVariantModel.objects.filter(sku="COFFEE-250").exists() is False

    def test_persists_and_round_trips_option_values_in_order(self) -> None:
        _seed_product("house-blend", "weight", "grind")
        repo = DjangoVariantRepository()

        stored = repo.add(
            _variant(
                "house-blend",
                "coffee-250",
                "250g Bag",
                values=(_value("weight", "250"), _value("grind", "espresso")),
            )
        )

        assert [(v.attribute.value, v.value) for v in stored.values] == [
            ("weight", "250"),
            ("grind", "espresso"),
        ]
        loaded = repo.get_by_sku("COFFEE-250")
        assert [(v.attribute.value, v.value) for v in loaded.values] == [
            ("weight", "250"),
            ("grind", "espresso"),
        ]
        rows = ProductVariantAttributeValueModel.objects.filter(variant_id=stored.id).order_by(
            "position"
        )
        assert [(r.attribute.code, r.position) for r in rows] == [("weight", 0), ("grind", 1)]

    def test_rejects_a_value_for_a_vanished_attribute(self) -> None:
        # Defensive guard for the concurrent-deletion race on a value's attribute.
        _seed_product("house-blend")

        with pytest.raises(UnknownAttributeError):
            DjangoVariantRepository().add(
                _variant(
                    "house-blend",
                    "coffee-250",
                    "250g Bag",
                    values=(_value("ghost", "x"),),
                )
            )

        # The whole insert rolled back: no half-built variant remains.
        assert ProductVariantModel.objects.filter(sku="COFFEE-250").exists() is False


class TestReads:
    def test_get_by_sku_round_trips_the_entity(self) -> None:
        _seed_product()
        repo = DjangoVariantRepository()
        repo.add(_variant("house-blend", "coffee-250", "250g Bag"))

        loaded = repo.get_by_sku("COFFEE-250")

        assert loaded.name == "250g Bag"
        assert loaded.product.value == "house-blend"

    def test_get_by_sku_raises_when_missing(self) -> None:
        with pytest.raises(VariantNotFoundError):
            DjangoVariantRepository().get_by_sku("GHOST")

    def test_exists_by_sku_reflects_persistence(self) -> None:
        _seed_product()
        repo = DjangoVariantRepository()
        assert repo.exists_by_sku("COFFEE-250") is False

        repo.add(_variant("house-blend", "coffee-250", "250g Bag"))
        assert repo.exists_by_sku("COFFEE-250") is True

    def test_list_for_product_returns_only_that_products_variants_sorted(self) -> None:
        _seed_product("house-blend")
        _other_product("tea-blend")
        repo = DjangoVariantRepository()
        repo.add(_variant("house-blend", "coffee-1000", "1kg Bag"))
        repo.add(_variant("house-blend", "coffee-250", "250g Bag"))
        repo.add(_variant("tea-blend", "tea-100", "100g Tin"))

        listed = repo.list_for_product("house-blend")

        assert [v.sku.value for v in listed] == ["COFFEE-1000", "COFFEE-250"]


def _other_product(code: str) -> None:
    DjangoProductRepository().add(
        Product(code=ProductCode(code), name=code.title(), product_type=ProductTypeCode("coffee"))
    )


def test_variant_model_str_is_the_sku() -> None:
    _seed_product()
    DjangoVariantRepository().add(_variant("house-blend", "coffee-250", "250g Bag"))

    assert str(ProductVariantModel.objects.get(sku="COFFEE-250")) == "COFFEE-250"


def test_variant_value_model_str_is_informative() -> None:
    _seed_product("house-blend", "weight")
    stored = DjangoVariantRepository().add(
        _variant("house-blend", "coffee-250", "250g Bag", values=(_value("weight", "250"),))
    )
    row = ProductVariantAttributeValueModel.objects.get(variant_id=stored.id)

    assert str(row) == f"{row.variant_id}:{row.attribute_id}"


class TestMedia:
    def test_persists_and_round_trips_media_in_order(self) -> None:
        _seed_product("house-blend")
        repo = DjangoVariantRepository()

        stored = repo.add(
            _variant(
                "house-blend",
                "coffee-250",
                "250g Bag",
                media=(
                    MediaAsset(url="/media/front.jpg", alt_text="Front"),
                    MediaAsset(url="/media/back.jpg"),
                ),
            )
        )

        assert [(m.url, m.alt_text) for m in stored.media] == [
            ("/media/front.jpg", "Front"),
            ("/media/back.jpg", ""),
        ]
        loaded = repo.get_by_sku("COFFEE-250")
        assert [m.url for m in loaded.media] == ["/media/front.jpg", "/media/back.jpg"]
        rows = ProductVariantMediaModel.objects.filter(variant_id=stored.id).order_by("position")
        assert [(r.url, r.position) for r in rows] == [
            ("/media/front.jpg", 0),
            ("/media/back.jpg", 1),
        ]

    def test_media_model_str_is_informative(self) -> None:
        _seed_product("house-blend")
        stored = DjangoVariantRepository().add(
            _variant(
                "house-blend",
                "coffee-250",
                "250g Bag",
                media=(MediaAsset(url="/media/front.jpg"),),
            )
        )
        row = ProductVariantMediaModel.objects.get(variant_id=stored.id)

        assert str(row) == f"{row.variant_id}:/media/front.jpg"
