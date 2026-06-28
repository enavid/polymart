"""Unit tests for the attribute-value conformance domain service.

This is where a product's free-form values are checked and canonicalized against
the typed attribute definitions: numbers as ``Decimal`` (never float), booleans as
literals, dropdowns against their declared choices, required attributes present.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.catalog.entities import Attribute
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    InvalidAttributeValueError,
    MissingRequiredAttributeError,
    UnassignedAttributeError,
)
from src.domain.catalog.services import normalize_attribute_values
from src.domain.catalog.value_objects import AttributeChoice, AttributeCode, AttributeValue


def _attribute(
    code: str,
    input_type: AttributeInputType,
    *,
    required: bool = False,
    choices: tuple[AttributeChoice, ...] = (),
) -> Attribute:
    return Attribute(
        code=AttributeCode(code),
        name=code.title(),
        input_type=input_type,
        required=required,
        choices=choices,
    )


def _value(code: str, value: str) -> AttributeValue:
    return AttributeValue(attribute=AttributeCode(code), value=value)


class TestAssignment:
    def test_rejects_a_value_for_an_unassigned_attribute(self) -> None:
        attributes = [_attribute("origin", AttributeInputType.PLAIN_TEXT)]

        with pytest.raises(UnassignedAttributeError):
            normalize_attribute_values(attributes, [_value("weight", "250")])

    def test_optional_attribute_may_be_omitted(self) -> None:
        attributes = [_attribute("origin", AttributeInputType.PLAIN_TEXT)]

        assert normalize_attribute_values(attributes, []) == ()

    def test_required_attribute_must_be_present(self) -> None:
        attributes = [_attribute("origin", AttributeInputType.PLAIN_TEXT, required=True)]

        with pytest.raises(MissingRequiredAttributeError):
            normalize_attribute_values(attributes, [])

    def test_preserves_the_product_types_declared_order(self) -> None:
        attributes = [
            _attribute("origin", AttributeInputType.PLAIN_TEXT),
            _attribute("roast-level", AttributeInputType.PLAIN_TEXT),
        ]

        normalized = normalize_attribute_values(
            attributes,
            [_value("roast-level", "dark"), _value("origin", "ethiopia")],
        )

        assert [v.attribute.value for v in normalized] == ["origin", "roast-level"]


class TestText:
    def test_trims_text(self) -> None:
        attributes = [_attribute("origin", AttributeInputType.PLAIN_TEXT)]

        normalized = normalize_attribute_values(attributes, [_value("origin", "  ethiopia ")])

        assert normalized[0].value == "ethiopia"

    def test_rejects_blank_text(self) -> None:
        attributes = [_attribute("origin", AttributeInputType.PLAIN_TEXT)]

        with pytest.raises(InvalidAttributeValueError):
            normalize_attribute_values(attributes, [_value("origin", "   ")])


class TestNumber:
    def test_parses_with_decimal_precision(self) -> None:
        attributes = [_attribute("weight", AttributeInputType.NUMBER)]

        normalized = normalize_attribute_values(attributes, [_value("weight", " 250.50 ")])

        # Decimal preserves the trailing zero a float would drop.
        assert normalized[0].value == "250.50"
        assert Decimal(normalized[0].value) == Decimal("250.50")

    def test_allows_a_negative_number(self) -> None:
        attributes = [_attribute("offset", AttributeInputType.NUMBER)]

        normalized = normalize_attribute_values(attributes, [_value("offset", "-3")])

        assert normalized[0].value == "-3"

    @pytest.mark.parametrize("raw", ["abc", "", "1,5", "NaN", "Infinity", "-Infinity"])
    def test_rejects_a_non_finite_or_non_numeric_value(self, raw: str) -> None:
        attributes = [_attribute("weight", AttributeInputType.NUMBER)]

        with pytest.raises(InvalidAttributeValueError):
            normalize_attribute_values(attributes, [_value("weight", raw)])


class TestBoolean:
    @pytest.mark.parametrize(("raw", "expected"), [("True", "true"), (" FALSE ", "false")])
    def test_normalizes_boolean_literals(self, raw: str, expected: str) -> None:
        attributes = [_attribute("organic", AttributeInputType.BOOLEAN)]

        normalized = normalize_attribute_values(attributes, [_value("organic", raw)])

        assert normalized[0].value == expected

    @pytest.mark.parametrize("raw", ["yes", "1", "", "maybe"])
    def test_rejects_a_non_boolean(self, raw: str) -> None:
        attributes = [_attribute("organic", AttributeInputType.BOOLEAN)]

        with pytest.raises(InvalidAttributeValueError):
            normalize_attribute_values(attributes, [_value("organic", raw)])


class TestDropdown:
    def _grind(self) -> Attribute:
        return _attribute(
            "grind",
            AttributeInputType.DROPDOWN,
            choices=(
                AttributeChoice(value="whole-bean", label="Whole bean"),
                AttributeChoice(value="espresso", label="Espresso"),
            ),
        )

    def test_accepts_a_declared_choice(self) -> None:
        normalized = normalize_attribute_values([self._grind()], [_value("grind", " espresso ")])

        assert normalized[0].value == "espresso"

    def test_rejects_an_undeclared_choice(self) -> None:
        with pytest.raises(InvalidAttributeValueError):
            normalize_attribute_values([self._grind()], [_value("grind", "turkish")])
