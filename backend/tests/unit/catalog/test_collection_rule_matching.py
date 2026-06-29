"""Unit tests for the rule-based collection domain rules (pure Python, no DB).

Two pure functions: ``reject_duplicate_conditions`` (a rule lists each condition
at most once) and ``match_products`` (which products a conjunction of conditions
selects, evaluated against their attribute values).
"""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Product
from src.domain.catalog.enums import RuleOperator
from src.domain.catalog.exceptions import DuplicateRuleConditionError
from src.domain.catalog.services import match_products, reject_duplicate_conditions
from src.domain.catalog.value_objects import (
    AttributeCode,
    AttributeValue,
    ProductCode,
    ProductTypeCode,
    RuleCondition,
)


def _condition(attribute: str, operator: RuleOperator, value: str) -> RuleCondition:
    return RuleCondition(attribute=AttributeCode(attribute), operator=operator, value=value)


def _product(code: str, **values: str) -> Product:
    return Product(
        code=ProductCode(code),
        name=code.title(),
        product_type=ProductTypeCode("coffee"),
        values=tuple(
            AttributeValue(attribute=AttributeCode(attr), value=value)
            for attr, value in values.items()
        ),
    )


class TestRejectDuplicateConditions:
    def test_returns_conditions_unchanged_when_unique(self) -> None:
        conditions = (
            _condition("roast-level", RuleOperator.EQUALS, "dark"),
            _condition("decaf", RuleOperator.NOT_EQUALS, "true"),
        )

        assert reject_duplicate_conditions(conditions) == conditions

    def test_accepts_an_empty_rule(self) -> None:
        assert reject_duplicate_conditions(()) == ()

    def test_allows_the_same_attribute_with_a_different_operator_or_value(self) -> None:
        # "roast-level != light AND roast-level != medium" is a meaningful rule.
        conditions = (
            _condition("roast-level", RuleOperator.NOT_EQUALS, "light"),
            _condition("roast-level", RuleOperator.NOT_EQUALS, "medium"),
        )

        assert reject_duplicate_conditions(conditions) == conditions

    def test_rejects_an_exact_duplicate_condition(self) -> None:
        with pytest.raises(DuplicateRuleConditionError):
            reject_duplicate_conditions(
                (
                    _condition("roast-level", RuleOperator.EQUALS, "dark"),
                    _condition("roast-level", RuleOperator.EQUALS, "dark"),
                )
            )


class TestMatchProducts:
    def test_empty_rule_matches_nothing(self) -> None:
        # A conjunction of zero conditions would be vacuously true; we deliberately
        # select nothing instead, so an unconfigured rule never sweeps in every product.
        products = [_product("house-blend", **{"roast-level": "dark"})]

        assert match_products((), products) == ()

    def test_equals_selects_products_with_the_matching_value(self) -> None:
        products = [
            _product("house-blend", **{"roast-level": "dark"}),
            _product("breakfast", **{"roast-level": "light"}),
        ]

        result = match_products((_condition("roast-level", RuleOperator.EQUALS, "dark"),), products)

        assert [p.value for p in result] == ["house-blend"]

    def test_equals_excludes_a_product_missing_the_attribute(self) -> None:
        products = [_product("mystery")]

        result = match_products((_condition("roast-level", RuleOperator.EQUALS, "dark"),), products)

        assert result == ()

    def test_not_equals_excludes_the_matching_value(self) -> None:
        products = [
            _product("house-blend", **{"roast-level": "dark"}),
            _product("breakfast", **{"roast-level": "light"}),
        ]

        result = match_products(
            (_condition("roast-level", RuleOperator.NOT_EQUALS, "dark"),), products
        )

        assert [p.value for p in result] == ["breakfast"]

    def test_not_equals_includes_a_product_missing_the_attribute(self) -> None:
        # A product with no value for the attribute is "not equal to" any value.
        products = [_product("mystery")]

        result = match_products(
            (_condition("roast-level", RuleOperator.NOT_EQUALS, "dark"),), products
        )

        assert [p.value for p in result] == ["mystery"]

    def test_conjunction_requires_every_condition_to_hold(self) -> None:
        products = [
            _product("a", **{"roast-level": "dark", "decaf": "false"}),
            _product("b", **{"roast-level": "dark", "decaf": "true"}),
            _product("c", **{"roast-level": "light", "decaf": "false"}),
        ]

        result = match_products(
            (
                _condition("roast-level", RuleOperator.EQUALS, "dark"),
                _condition("decaf", RuleOperator.EQUALS, "false"),
            ),
            products,
        )

        assert [p.value for p in result] == ["a"]

    def test_preserves_the_input_product_order(self) -> None:
        products = [
            _product("cold-brew", **{"roast-level": "dark"}),
            _product("house-blend", **{"roast-level": "dark"}),
        ]

        result = match_products((_condition("roast-level", RuleOperator.EQUALS, "dark"),), products)

        assert [p.value for p in result] == ["cold-brew", "house-blend"]
