"""Unit tests for the ProductVariant entity's structural rules (pure domain)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import ProductVariant
from src.domain.catalog.exceptions import (
    DuplicateAttributeValueError,
    DuplicateMediaAssetError,
    InvalidVariantNameError,
)
from src.domain.catalog.value_objects import (
    AttributeCode,
    AttributeValue,
    MediaAsset,
    ProductCode,
    Sku,
)


def _variant(**overrides: object) -> ProductVariant:
    defaults: dict[str, object] = {
        "product": ProductCode("house-blend"),
        "sku": Sku("coffee-250"),
        "name": "250g Bag",
    }
    defaults.update(overrides)
    return ProductVariant(**defaults)  # type: ignore[arg-type]


def _value(code: str, value: str) -> AttributeValue:
    return AttributeValue(attribute=AttributeCode(code), value=value)


class TestConstruction:
    def test_pairs_a_product_with_a_sku_and_name(self) -> None:
        variant = _variant()

        assert variant.product.value == "house-blend"
        assert variant.sku.value == "COFFEE-250"
        assert variant.name == "250g Bag"
        assert variant.values == ()
        assert variant.id is None


class TestOptionValues:
    """A variant carries its own option values (variant-level attributes). The
    entity owns only the structural rule -- at most one value per attribute;
    conformance to the type's variant attributes is the domain service's job."""

    def test_keeps_its_option_values(self) -> None:
        variant = _variant(values=(_value("weight", "250"), _value("grind", "espresso")))

        assert [(v.attribute.value, v.value) for v in variant.values] == [
            ("weight", "250"),
            ("grind", "espresso"),
        ]

    def test_rejects_two_values_for_the_same_attribute(self) -> None:
        with pytest.raises(DuplicateAttributeValueError):
            _variant(values=(_value("weight", "250"), _value("weight", "1000")))


class TestMedia:
    """A variant carries an ordered list of media assets (images). The entity owns
    the structural rule: the same URL is never listed twice."""

    def test_keeps_media_in_order(self) -> None:
        variant = _variant(
            media=(
                MediaAsset(url="/media/front.jpg", alt_text="Front"),
                MediaAsset(url="/media/back.jpg"),
            )
        )

        assert [m.url for m in variant.media] == ["/media/front.jpg", "/media/back.jpg"]
        assert variant.media[0].alt_text == "Front"

    def test_defaults_to_no_media(self) -> None:
        assert _variant().media == ()

    def test_rejects_a_duplicate_media_url(self) -> None:
        with pytest.raises(DuplicateMediaAssetError):
            _variant(
                media=(
                    MediaAsset(url="/media/front.jpg"),
                    MediaAsset(url="/media/front.jpg", alt_text="Same image again"),
                )
            )


class TestName:
    def test_trims_the_name(self) -> None:
        assert _variant(name="  250g Bag  ").name == "250g Bag"

    @pytest.mark.parametrize("raw", ["", "   ", "x" * 256])
    def test_rejects_a_blank_or_overlong_name(self, raw: str) -> None:
        with pytest.raises(InvalidVariantNameError):
            _variant(name=raw)
