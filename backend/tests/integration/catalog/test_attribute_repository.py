"""Integration tests for the Django attribute repository (real DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Attribute
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    AttributeNotFoundError,
)
from src.domain.catalog.value_objects import AttributeChoice, AttributeCode
from src.infrastructure.catalog.models import AttributeChoiceModel, AttributeModel
from src.infrastructure.catalog.repositories import DjangoAttributeRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _dropdown() -> Attribute:
    return Attribute(
        code=AttributeCode("roast-level"),
        name="Roast level",
        input_type=AttributeInputType.DROPDOWN,
        choices=(
            AttributeChoice(value="light", label="Light"),
            AttributeChoice(value="dark", label="Dark"),
        ),
    )


class TestAdd:
    def test_persists_a_text_attribute_and_assigns_an_id(self) -> None:
        repo = DjangoAttributeRepository()

        stored = repo.add(
            Attribute(
                code=AttributeCode("origin"),
                name="Origin",
                input_type=AttributeInputType.PLAIN_TEXT,
            )
        )

        assert stored.id is not None
        assert AttributeModel.objects.filter(code="origin").exists()

    def test_persists_a_dropdown_with_its_choices_in_order(self) -> None:
        repo = DjangoAttributeRepository()

        stored = repo.add(_dropdown())

        assert [c.value for c in stored.choices] == ["light", "dark"]
        rows = AttributeChoiceModel.objects.filter(attribute_id=stored.id).order_by("position")
        assert [(r.value, r.position) for r in rows] == [("light", 0), ("dark", 1)]

    def test_rejects_a_duplicate_code(self) -> None:
        repo = DjangoAttributeRepository()
        repo.add(
            Attribute(
                code=AttributeCode("origin"),
                name="Origin",
                input_type=AttributeInputType.PLAIN_TEXT,
            )
        )

        with pytest.raises(AttributeAlreadyExistsError):
            repo.add(
                Attribute(
                    code=AttributeCode("origin"),
                    name="Origin Again",
                    input_type=AttributeInputType.NUMBER,
                )
            )


class TestReads:
    def test_get_by_code_round_trips_the_entity(self) -> None:
        repo = DjangoAttributeRepository()
        repo.add(_dropdown())

        loaded = repo.get_by_code("roast-level")

        assert loaded.input_type is AttributeInputType.DROPDOWN
        assert [c.label for c in loaded.choices] == ["Light", "Dark"]

    def test_get_by_code_raises_when_missing(self) -> None:
        with pytest.raises(AttributeNotFoundError):
            DjangoAttributeRepository().get_by_code("ghost")

    def test_exists_by_code_reflects_persistence(self) -> None:
        repo = DjangoAttributeRepository()
        assert repo.exists_by_code("origin") is False

        repo.add(
            Attribute(
                code=AttributeCode("origin"),
                name="Origin",
                input_type=AttributeInputType.PLAIN_TEXT,
            )
        )
        assert repo.exists_by_code("origin") is True

    def test_list_all_returns_attributes_sorted_by_code(self) -> None:
        repo = DjangoAttributeRepository()
        repo.add(
            Attribute(
                code=AttributeCode("origin"),
                name="Origin",
                input_type=AttributeInputType.PLAIN_TEXT,
            )
        )
        repo.add(_dropdown())

        codes = [a.code.value for a in repo.list_all()]

        assert codes == ["origin", "roast-level"]


def test_choice_model_str_is_informative() -> None:
    attribute = AttributeModel.objects.create(
        code="roast-level", name="Roast", input_type="dropdown"
    )
    choice = AttributeChoiceModel.objects.create(attribute=attribute, value="light", label="Light")

    assert str(attribute) == "roast-level"
    assert str(choice) == f"{attribute.id}:light"
