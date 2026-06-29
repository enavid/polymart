"""Integration tests for the Django collection-rule repository (real DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Attribute, Collection
from src.domain.catalog.enums import AttributeInputType, RuleOperator
from src.domain.catalog.exceptions import CollectionNotFoundError, UnknownAttributeError
from src.domain.catalog.value_objects import (
    AttributeCode,
    CollectionSlug,
    RuleCondition,
)
from src.infrastructure.catalog.models import CollectionRuleConditionModel
from src.infrastructure.catalog.repositories import (
    DjangoAttributeRepository,
    DjangoCollectionRepository,
    DjangoCollectionRuleRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed_collection(slug: str = "dark-roasts") -> None:
    DjangoCollectionRepository().add(Collection(slug=CollectionSlug(slug), name=slug.title()))


def _seed_attributes(*codes: str) -> None:
    repo = DjangoAttributeRepository()
    for code in codes:
        repo.add(
            Attribute(
                code=AttributeCode(code),
                name=code.title(),
                input_type=AttributeInputType.PLAIN_TEXT,
            )
        )


def _condition(attribute: str, operator: RuleOperator, value: str) -> RuleCondition:
    return RuleCondition(attribute=AttributeCode(attribute), operator=operator, value=value)


class TestReplace:
    def test_stores_conditions_in_order(self) -> None:
        _seed_collection()
        _seed_attributes("roast-level", "decaf")
        repo = DjangoCollectionRuleRepository()

        result = repo.replace(
            "dark-roasts",
            (
                _condition("decaf", RuleOperator.NOT_EQUALS, "true"),
                _condition("roast-level", RuleOperator.EQUALS, "dark"),
            ),
        )

        assert [(c.attribute.value, c.operator, c.value) for c in result] == [
            ("decaf", RuleOperator.NOT_EQUALS, "true"),
            ("roast-level", RuleOperator.EQUALS, "dark"),
        ]

    def test_replacing_overwrites_the_previous_rule(self) -> None:
        _seed_collection()
        _seed_attributes("roast-level", "decaf")
        repo = DjangoCollectionRuleRepository()
        repo.replace("dark-roasts", (_condition("roast-level", RuleOperator.EQUALS, "dark"),))

        result = repo.replace("dark-roasts", (_condition("decaf", RuleOperator.EQUALS, "true"),))

        assert [c.attribute.value for c in result] == ["decaf"]
        rows = CollectionRuleConditionModel.objects.filter(collection__slug="dark-roasts")
        assert rows.count() == 1

    def test_replacing_with_an_empty_rule_clears_it(self) -> None:
        _seed_collection()
        _seed_attributes("roast-level")
        repo = DjangoCollectionRuleRepository()
        repo.replace("dark-roasts", (_condition("roast-level", RuleOperator.EQUALS, "dark"),))

        result = repo.replace("dark-roasts", ())

        assert result == ()
        rows = CollectionRuleConditionModel.objects.filter(collection__slug="dark-roasts")
        assert not rows.exists()

    def test_raises_if_the_collection_vanished(self) -> None:
        with pytest.raises(CollectionNotFoundError):
            DjangoCollectionRuleRepository().replace(
                "ghost", (_condition("roast-level", RuleOperator.EQUALS, "dark"),)
            )

    def test_raises_and_rolls_back_if_an_attribute_vanished(self) -> None:
        # Defends the use case's check-then-act window: an attribute was validated,
        # then deleted before this replace ran. The whole replace must roll back.
        _seed_collection()
        _seed_attributes("roast-level")
        repo = DjangoCollectionRuleRepository()
        repo.replace("dark-roasts", (_condition("roast-level", RuleOperator.EQUALS, "dark"),))

        with pytest.raises(UnknownAttributeError):
            repo.replace("dark-roasts", (_condition("ghost", RuleOperator.EQUALS, "x"),))

        # The prior rule is untouched (the delete was rolled back).
        assert [c.attribute.value for c in repo.list_for_collection("dark-roasts")] == [
            "roast-level"
        ]


class TestListForCollection:
    def test_returns_conditions_in_assignment_order(self) -> None:
        _seed_collection()
        _seed_attributes("roast-level", "decaf")
        repo = DjangoCollectionRuleRepository()
        repo.replace(
            "dark-roasts",
            (
                _condition("decaf", RuleOperator.NOT_EQUALS, "true"),
                _condition("roast-level", RuleOperator.EQUALS, "dark"),
            ),
        )

        result = repo.list_for_collection("dark-roasts")

        assert [c.attribute.value for c in result] == ["decaf", "roast-level"]

    def test_returns_empty_for_a_collection_without_a_rule(self) -> None:
        _seed_collection()

        assert DjangoCollectionRuleRepository().list_for_collection("dark-roasts") == ()


def test_collection_rule_condition_model_str_is_informative() -> None:
    _seed_collection()
    _seed_attributes("roast-level")
    DjangoCollectionRuleRepository().replace(
        "dark-roasts", (_condition("roast-level", RuleOperator.EQUALS, "dark"),)
    )

    condition = CollectionRuleConditionModel.objects.get(collection__slug="dark-roasts")
    assert str(condition) == f"{condition.collection_id}:roast-level:equals:dark"
