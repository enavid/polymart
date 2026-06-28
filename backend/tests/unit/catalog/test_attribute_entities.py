"""Unit tests for the Attribute entity and its invariants."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Attribute
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeChoicesNotAllowedError,
    AttributeChoicesRequiredError,
    DuplicateAttributeChoiceError,
    InvalidAttributeNameError,
)
from src.domain.catalog.value_objects import AttributeChoice, AttributeCode


def _choice(value: str, label: str | None = None) -> AttributeChoice:
    return AttributeChoice(value=value, label=label or value.title())


class TestAttributeName:
    def test_trims_the_display_name(self) -> None:
        attribute = Attribute(
            code=AttributeCode("origin"),
            name="  Origin ",
            input_type=AttributeInputType.PLAIN_TEXT,
        )

        assert attribute.name == "Origin"

    @pytest.mark.parametrize("name", ["", "   ", "n" * 256])
    def test_rejects_a_blank_or_overlong_name(self, name: str) -> None:
        with pytest.raises(InvalidAttributeNameError):
            Attribute(
                code=AttributeCode("origin"),
                name=name,
                input_type=AttributeInputType.PLAIN_TEXT,
            )


class TestChoiceTypeRules:
    def test_a_dropdown_must_carry_at_least_one_choice(self) -> None:
        with pytest.raises(AttributeChoicesRequiredError):
            Attribute(
                code=AttributeCode("roast-level"),
                name="Roast level",
                input_type=AttributeInputType.DROPDOWN,
            )

    def test_a_dropdown_accepts_its_choices(self) -> None:
        attribute = Attribute(
            code=AttributeCode("roast-level"),
            name="Roast level",
            input_type=AttributeInputType.DROPDOWN,
            choices=(_choice("light"), _choice("dark")),
        )

        assert [c.value for c in attribute.choices] == ["light", "dark"]

    @pytest.mark.parametrize(
        "input_type",
        [
            AttributeInputType.PLAIN_TEXT,
            AttributeInputType.NUMBER,
            AttributeInputType.BOOLEAN,
        ],
    )
    def test_a_non_choice_type_must_not_carry_choices(
        self, input_type: AttributeInputType
    ) -> None:
        with pytest.raises(AttributeChoicesNotAllowedError):
            Attribute(
                code=AttributeCode("origin"),
                name="Origin",
                input_type=input_type,
                choices=(_choice("light"),),
            )

    def test_rejects_duplicate_choice_values(self) -> None:
        with pytest.raises(DuplicateAttributeChoiceError):
            Attribute(
                code=AttributeCode("roast-level"),
                name="Roast level",
                input_type=AttributeInputType.DROPDOWN,
                choices=(_choice("light"), _choice("light", "Light again")),
            )


class TestInputTypeMetadata:
    def test_only_the_dropdown_is_a_choice_type(self) -> None:
        assert AttributeInputType.DROPDOWN.is_choice_type is True
        assert AttributeInputType.PLAIN_TEXT.is_choice_type is False
        assert AttributeInputType.NUMBER.is_choice_type is False
        assert AttributeInputType.BOOLEAN.is_choice_type is False
