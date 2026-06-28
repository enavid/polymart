"""Unit tests for the catalog value objects (pure domain, no framework)."""

from __future__ import annotations

import pytest

from src.domain.catalog.exceptions import (
    InvalidAttributeChoiceError,
    InvalidAttributeCodeError,
)
from src.domain.catalog.value_objects import AttributeChoice, AttributeCode


class TestAttributeCode:
    def test_accepts_kebab_case_and_keeps_the_canonical_value(self) -> None:
        code = AttributeCode("  roast-level ")

        assert code.value == "roast-level"
        assert str(code) == "roast-level"

    @pytest.mark.parametrize(
        "raw",
        ["", "   ", "Roast", "roast_level", "roast level", "-roast", "roast-", "a" * 65],
    )
    def test_rejects_malformed_codes(self, raw: str) -> None:
        with pytest.raises(InvalidAttributeCodeError):
            AttributeCode(raw)

    def test_equality_is_by_value(self) -> None:
        assert AttributeCode("origin") == AttributeCode("origin")


class TestAttributeChoice:
    def test_accepts_a_slug_value_and_a_display_label(self) -> None:
        choice = AttributeChoice(value=" light ", label="  Light roast ")

        assert choice.value == "light"
        assert choice.label == "Light roast"

    @pytest.mark.parametrize("value", ["", "  ", "Light", "light roast", "a" * 65])
    def test_rejects_a_malformed_value(self, value: str) -> None:
        with pytest.raises(InvalidAttributeChoiceError):
            AttributeChoice(value=value, label="Light")

    @pytest.mark.parametrize("label", ["", "   ", "x" * 256])
    def test_rejects_a_blank_or_overlong_label(self, label: str) -> None:
        with pytest.raises(InvalidAttributeChoiceError):
            AttributeChoice(value="light", label=label)
