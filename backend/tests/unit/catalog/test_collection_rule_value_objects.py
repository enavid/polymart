"""Unit tests for the rule-based collection value objects (pure Python, no DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.enums import RuleOperator
from src.domain.catalog.exceptions import InvalidRuleConditionError
from src.domain.catalog.value_objects import AttributeCode, RuleCondition


class TestRuleOperator:
    def test_has_equals_and_not_equals(self) -> None:
        assert RuleOperator("equals") is RuleOperator.EQUALS
        assert RuleOperator("not_equals") is RuleOperator.NOT_EQUALS


class TestRuleCondition:
    def test_keeps_a_well_formed_condition(self) -> None:
        condition = RuleCondition(
            attribute=AttributeCode("roast-level"), operator=RuleOperator.EQUALS, value="dark"
        )

        assert condition.attribute.value == "roast-level"
        assert condition.operator is RuleOperator.EQUALS
        assert condition.value == "dark"

    def test_trims_surrounding_whitespace_from_the_value(self) -> None:
        condition = RuleCondition(
            attribute=AttributeCode("roast-level"), operator=RuleOperator.EQUALS, value="  dark  "
        )

        assert condition.value == "dark"

    def test_rejects_a_blank_value(self) -> None:
        with pytest.raises(InvalidRuleConditionError):
            RuleCondition(
                attribute=AttributeCode("roast-level"), operator=RuleOperator.EQUALS, value="   "
            )

    def test_rejects_an_overlong_value(self) -> None:
        with pytest.raises(InvalidRuleConditionError):
            RuleCondition(
                attribute=AttributeCode("roast-level"),
                operator=RuleOperator.EQUALS,
                value="x" * 1025,
            )

    def test_is_immutable(self) -> None:
        condition = RuleCondition(
            attribute=AttributeCode("roast-level"), operator=RuleOperator.EQUALS, value="dark"
        )

        with pytest.raises(AttributeError):
            condition.value = "light"  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        left = RuleCondition(AttributeCode("roast-level"), RuleOperator.EQUALS, "dark")
        right = RuleCondition(AttributeCode("roast-level"), RuleOperator.EQUALS, "dark")

        assert left == right
