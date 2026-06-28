"""Integration tests for the Django product-type repository (real DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Attribute, ProductType
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    ProductTypeAlreadyExistsError,
    ProductTypeNotFoundError,
    UnknownAttributeError,
)
from src.domain.catalog.value_objects import AttributeCode, ProductTypeCode
from src.infrastructure.catalog.models import (
    VARIANT_ATTRIBUTE_KIND,
    ProductTypeAttributeModel,
    ProductTypeModel,
)
from src.infrastructure.catalog.repositories import (
    DjangoAttributeRepository,
    DjangoProductTypeRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


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


class TestAdd:
    def test_persists_with_attribute_links_in_declared_order(self) -> None:
        _seed_attributes("roast-level", "origin")
        repo = DjangoProductTypeRepository()

        stored = repo.add(
            ProductType(
                code=ProductTypeCode("coffee"),
                name="Coffee",
                attributes=(AttributeCode("roast-level"), AttributeCode("origin")),
            )
        )

        assert stored.id is not None
        assert [a.value for a in stored.attributes] == ["roast-level", "origin"]
        rows = ProductTypeAttributeModel.objects.filter(product_type_id=stored.id).order_by(
            "position"
        )
        assert [(r.attribute.code, r.position) for r in rows] == [
            ("roast-level", 0),
            ("origin", 1),
        ]

    def test_persists_and_round_trips_both_attribute_levels(self) -> None:
        _seed_attributes("origin", "weight", "grind")
        repo = DjangoProductTypeRepository()

        stored = repo.add(
            ProductType(
                code=ProductTypeCode("coffee"),
                name="Coffee",
                attributes=(AttributeCode("origin"),),
                variant_attributes=(AttributeCode("weight"), AttributeCode("grind")),
            )
        )

        # Returned entity keeps each level in its declared order.
        assert [a.value for a in stored.attributes] == ["origin"]
        assert [a.value for a in stored.variant_attributes] == ["weight", "grind"]
        # And a fresh read reconstructs the same split.
        loaded = repo.get_by_code("coffee")
        assert [a.value for a in loaded.attributes] == ["origin"]
        assert [a.value for a in loaded.variant_attributes] == ["weight", "grind"]
        # Variant links carry the variant kind, positioned within their own level.
        variant_rows = ProductTypeAttributeModel.objects.filter(
            product_type_id=stored.id, kind=VARIANT_ATTRIBUTE_KIND
        ).order_by("position")
        assert [(r.attribute.code, r.position) for r in variant_rows] == [
            ("weight", 0),
            ("grind", 1),
        ]

    def test_rejects_a_reference_to_a_vanished_variant_attribute(self) -> None:
        # Defensive guard for the concurrent-deletion race on a variant attribute.
        repo = DjangoProductTypeRepository()

        with pytest.raises(UnknownAttributeError):
            repo.add(
                ProductType(
                    code=ProductTypeCode("coffee"),
                    name="Coffee",
                    variant_attributes=(AttributeCode("ghost"),),
                )
            )

        assert ProductTypeModel.objects.filter(code="coffee").exists() is False

    def test_persists_a_type_without_attributes(self) -> None:
        stored = DjangoProductTypeRepository().add(
            ProductType(code=ProductTypeCode("misc"), name="Misc")
        )

        assert stored.attributes == ()
        assert ProductTypeModel.objects.filter(code="misc").exists()

    def test_rejects_a_duplicate_code(self) -> None:
        repo = DjangoProductTypeRepository()
        repo.add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))

        with pytest.raises(ProductTypeAlreadyExistsError):
            repo.add(ProductType(code=ProductTypeCode("coffee"), name="Coffee Again"))

    def test_rejects_a_reference_to_an_attribute_that_does_not_exist(self) -> None:
        # The use case validates attribute existence; this exercises the
        # repository's own defensive guard for the concurrent-deletion race,
        # where a validated attribute vanishes before the links are written.
        repo = DjangoProductTypeRepository()

        with pytest.raises(UnknownAttributeError):
            repo.add(
                ProductType(
                    code=ProductTypeCode("coffee"),
                    name="Coffee",
                    attributes=(AttributeCode("ghost"),),
                )
            )

        # The whole insert rolled back: no half-built product type remains.
        assert ProductTypeModel.objects.filter(code="coffee").exists() is False


class TestReads:
    def test_get_by_code_round_trips_the_entity(self) -> None:
        _seed_attributes("origin")
        repo = DjangoProductTypeRepository()
        repo.add(
            ProductType(
                code=ProductTypeCode("coffee"),
                name="Coffee",
                attributes=(AttributeCode("origin"),),
            )
        )

        loaded = repo.get_by_code("coffee")

        assert loaded.name == "Coffee"
        assert [a.value for a in loaded.attributes] == ["origin"]

    def test_get_by_code_raises_when_missing(self) -> None:
        with pytest.raises(ProductTypeNotFoundError):
            DjangoProductTypeRepository().get_by_code("ghost")

    def test_exists_by_code_reflects_persistence(self) -> None:
        repo = DjangoProductTypeRepository()
        assert repo.exists_by_code("coffee") is False

        repo.add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
        assert repo.exists_by_code("coffee") is True

    def test_list_all_returns_types_sorted_by_code(self) -> None:
        repo = DjangoProductTypeRepository()
        repo.add(ProductType(code=ProductTypeCode("tea"), name="Tea"))
        repo.add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))

        assert [t.code.value for t in repo.list_all()] == ["coffee", "tea"]


def test_link_model_str_is_informative() -> None:
    _seed_attributes("origin")
    stored = DjangoProductTypeRepository().add(
        ProductType(
            code=ProductTypeCode("coffee"),
            name="Coffee",
            attributes=(AttributeCode("origin"),),
        )
    )
    link = ProductTypeAttributeModel.objects.get(product_type_id=stored.id)

    assert str(ProductTypeModel.objects.get(code="coffee")) == "coffee"
    assert str(link) == f"{link.product_type_id}:{link.attribute_id}"
