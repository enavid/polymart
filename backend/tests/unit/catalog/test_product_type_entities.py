"""Unit tests for the ProductType entity and the ProductTypeCode value object."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import ProductType
from src.domain.catalog.exceptions import (
    DuplicateAttributeAssignmentError,
    InvalidProductTypeCodeError,
    InvalidProductTypeNameError,
)
from src.domain.catalog.value_objects import AttributeCode, ProductTypeCode


class TestProductTypeCode:
    def test_accepts_kebab_case_and_keeps_the_canonical_value(self) -> None:
        code = ProductTypeCode("  ground-coffee ")

        assert code.value == "ground-coffee"
        assert str(code) == "ground-coffee"

    @pytest.mark.parametrize("raw", ["", "   ", "Coffee", "ground_coffee", "-x", "x-", "a" * 65])
    def test_rejects_malformed_codes(self, raw: str) -> None:
        with pytest.raises(InvalidProductTypeCodeError):
            ProductTypeCode(raw)

    def test_equality_is_by_value(self) -> None:
        assert ProductTypeCode("coffee") == ProductTypeCode("coffee")


class TestProductType:
    def test_keeps_its_attribute_references_in_order(self) -> None:
        product_type = ProductType(
            code=ProductTypeCode("coffee"),
            name="Coffee",
            attributes=(AttributeCode("roast-level"), AttributeCode("origin")),
        )

        assert [a.value for a in product_type.attributes] == ["roast-level", "origin"]

    def test_a_type_may_declare_no_attributes(self) -> None:
        product_type = ProductType(code=ProductTypeCode("misc"), name="Misc")

        assert product_type.attributes == ()

    def test_trims_the_display_name(self) -> None:
        product_type = ProductType(code=ProductTypeCode("coffee"), name="  Coffee ")

        assert product_type.name == "Coffee"

    @pytest.mark.parametrize("name", ["", "   ", "n" * 256])
    def test_rejects_a_blank_or_overlong_name(self, name: str) -> None:
        with pytest.raises(InvalidProductTypeNameError):
            ProductType(code=ProductTypeCode("coffee"), name=name)

    def test_rejects_a_duplicate_attribute_reference(self) -> None:
        with pytest.raises(DuplicateAttributeAssignmentError):
            ProductType(
                code=ProductTypeCode("coffee"),
                name="Coffee",
                attributes=(AttributeCode("origin"), AttributeCode("origin")),
            )
