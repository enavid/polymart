"""Unit tests for the Product entity's structural rules (pure domain)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Product
from src.domain.catalog.exceptions import (
    DuplicateAttributeValueError,
    InvalidProductMetadataError,
    InvalidProductNameError,
)
from src.domain.catalog.value_objects import (
    AttributeCode,
    AttributeValue,
    ProductCode,
    ProductTypeCode,
)


def _product(**overrides: object) -> Product:
    defaults: dict[str, object] = {
        "code": ProductCode("coffee"),
        "name": "House Blend",
        "product_type": ProductTypeCode("coffee"),
    }
    defaults.update(overrides)
    return Product(**defaults)  # type: ignore[arg-type]


class TestName:
    def test_trims_the_name(self) -> None:
        assert _product(name="  House Blend  ").name == "House Blend"

    @pytest.mark.parametrize("raw", ["", "   ", "x" * 256])
    def test_rejects_a_blank_or_overlong_name(self, raw: str) -> None:
        with pytest.raises(InvalidProductNameError):
            _product(name=raw)


class TestValues:
    def test_keeps_values_in_given_order(self) -> None:
        product = _product(
            values=(
                AttributeValue(attribute=AttributeCode("origin"), value="ethiopia"),
                AttributeValue(attribute=AttributeCode("roast-level"), value="dark"),
            )
        )

        assert [v.attribute.value for v in product.values] == ["origin", "roast-level"]

    def test_rejects_two_values_for_the_same_attribute(self) -> None:
        with pytest.raises(DuplicateAttributeValueError):
            _product(
                values=(
                    AttributeValue(attribute=AttributeCode("origin"), value="ethiopia"),
                    AttributeValue(attribute=AttributeCode("origin"), value="kenya"),
                )
            )


class TestMetadata:
    def test_defaults_to_empty(self) -> None:
        assert _product().metadata == {}

    def test_trims_keys(self) -> None:
        assert _product(metadata={"  origin-note  ": "single estate"}).metadata == {
            "origin-note": "single estate"
        }

    @pytest.mark.parametrize("key", ["", "   ", "k" * 65])
    def test_rejects_a_blank_or_overlong_key(self, key: str) -> None:
        with pytest.raises(InvalidProductMetadataError):
            _product(metadata={key: "value"})

    def test_rejects_an_overlong_value(self) -> None:
        with pytest.raises(InvalidProductMetadataError):
            _product(metadata={"note": "v" * 1025})
