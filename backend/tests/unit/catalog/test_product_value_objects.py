"""Unit tests for the product value objects (pure domain, no Django)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.domain.catalog.exceptions import InvalidProductCodeError
from src.domain.catalog.value_objects import AttributeCode, AttributeValue, ProductCode


class TestProductCode:
    def test_accepts_a_kebab_slug(self) -> None:
        assert ProductCode("ethiopia-yirgacheffe").value == "ethiopia-yirgacheffe"

    def test_trims_surrounding_whitespace(self) -> None:
        assert ProductCode("  coffee  ").value == "coffee"

    def test_str_is_the_code(self) -> None:
        assert str(ProductCode("coffee")) == "coffee"

    @pytest.mark.parametrize("raw", ["", "  ", "Not A Slug", "trailing-", "UPPER", "a" * 65])
    def test_rejects_malformed_codes(self, raw: str) -> None:
        with pytest.raises(InvalidProductCodeError):
            ProductCode(raw)

    def test_is_immutable(self) -> None:
        with pytest.raises(FrozenInstanceError):
            ProductCode("coffee").value = "tea"  # type: ignore[misc]


class TestAttributeValue:
    def test_pairs_a_code_with_its_stored_string(self) -> None:
        value = AttributeValue(attribute=AttributeCode("origin"), value="ethiopia")

        assert value.attribute.value == "origin"
        assert value.value == "ethiopia"

    def test_equality_is_by_value(self) -> None:
        a = AttributeValue(attribute=AttributeCode("origin"), value="ethiopia")
        b = AttributeValue(attribute=AttributeCode("origin"), value="ethiopia")

        assert a == b
