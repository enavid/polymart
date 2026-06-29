"""Integration tests for the Django product repository (real DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Attribute, Product, ProductType
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    ProductAlreadyExistsError,
    ProductNotFoundError,
    ProductTypeNotFoundError,
    UnknownAttributeError,
)
from src.domain.catalog.value_objects import (
    AttributeCode,
    AttributeValue,
    ProductCode,
    ProductTypeCode,
)
from src.infrastructure.catalog.models import (
    ProductAttributeValueModel,
    ProductModel,
)
from src.infrastructure.catalog.repositories import (
    DjangoAttributeRepository,
    DjangoProductRepository,
    DjangoProductTypeRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _seed_catalog(*attribute_codes: str) -> None:
    """Create the given attributes and a 'coffee' product type assigning them."""
    attributes = DjangoAttributeRepository()
    for code in attribute_codes:
        attributes.add(
            Attribute(
                code=AttributeCode(code),
                name=code.title(),
                input_type=AttributeInputType.PLAIN_TEXT,
            )
        )
    DjangoProductTypeRepository().add(
        ProductType(
            code=ProductTypeCode("coffee"),
            name="Coffee",
            attributes=tuple(AttributeCode(code) for code in attribute_codes),
        )
    )


def _value(code: str, value: str) -> AttributeValue:
    return AttributeValue(attribute=AttributeCode(code), value=value)


class TestAdd:
    def test_persists_with_values_in_order_and_metadata(self) -> None:
        _seed_catalog("origin", "roast-level")
        repo = DjangoProductRepository()

        stored = repo.add(
            Product(
                code=ProductCode("house-blend"),
                name="House Blend",
                product_type=ProductTypeCode("coffee"),
                values=(_value("origin", "ethiopia"), _value("roast-level", "dark")),
                metadata={"supplier": "ACME"},
            )
        )

        assert stored.id is not None
        assert [(v.attribute.value, v.value) for v in stored.values] == [
            ("origin", "ethiopia"),
            ("roast-level", "dark"),
        ]
        assert stored.metadata == {"supplier": "ACME"}
        rows = ProductAttributeValueModel.objects.filter(product_id=stored.id).order_by("position")
        assert [(r.attribute.code, r.position) for r in rows] == [("origin", 0), ("roast-level", 1)]

    def test_persists_a_product_with_no_values(self) -> None:
        _seed_catalog()
        stored = DjangoProductRepository().add(
            Product(
                code=ProductCode("plain"),
                name="Plain",
                product_type=ProductTypeCode("coffee"),
            )
        )

        assert stored.values == ()
        assert ProductModel.objects.filter(code="plain").exists()

    def test_rejects_a_duplicate_code(self) -> None:
        _seed_catalog()
        repo = DjangoProductRepository()
        repo.add(
            Product(
                code=ProductCode("house-blend"),
                name="House Blend",
                product_type=ProductTypeCode("coffee"),
            )
        )

        with pytest.raises(ProductAlreadyExistsError):
            repo.add(
                Product(
                    code=ProductCode("house-blend"),
                    name="Again",
                    product_type=ProductTypeCode("coffee"),
                )
            )

    def test_rejects_an_unknown_product_type(self) -> None:
        # Defensive guard: the use case resolves the type; this exercises the
        # repository path where it has vanished (concurrent-deletion race).
        with pytest.raises(ProductTypeNotFoundError):
            DjangoProductRepository().add(
                Product(
                    code=ProductCode("house-blend"),
                    name="House Blend",
                    product_type=ProductTypeCode("ghost"),
                )
            )

        assert ProductModel.objects.filter(code="house-blend").exists() is False

    def test_rejects_a_value_for_a_vanished_attribute(self) -> None:
        # Defensive guard for the concurrent-deletion race on a value's attribute.
        _seed_catalog()

        with pytest.raises(UnknownAttributeError):
            DjangoProductRepository().add(
                Product(
                    code=ProductCode("house-blend"),
                    name="House Blend",
                    product_type=ProductTypeCode("coffee"),
                    values=(_value("ghost", "x"),),
                )
            )

        # The whole insert rolled back: no half-built product remains.
        assert ProductModel.objects.filter(code="house-blend").exists() is False


class TestReads:
    def test_get_by_code_round_trips_the_entity(self) -> None:
        _seed_catalog("origin")
        repo = DjangoProductRepository()
        repo.add(
            Product(
                code=ProductCode("house-blend"),
                name="House Blend",
                product_type=ProductTypeCode("coffee"),
                values=(_value("origin", "ethiopia"),),
                metadata={"supplier": "ACME"},
            )
        )

        loaded = repo.get_by_code("house-blend")

        assert loaded.name == "House Blend"
        assert loaded.product_type.value == "coffee"
        assert [(v.attribute.value, v.value) for v in loaded.values] == [("origin", "ethiopia")]
        assert loaded.metadata == {"supplier": "ACME"}

    def test_get_by_code_raises_when_missing(self) -> None:
        with pytest.raises(ProductNotFoundError):
            DjangoProductRepository().get_by_code("ghost")

    def test_exists_by_code_reflects_persistence(self) -> None:
        _seed_catalog()
        repo = DjangoProductRepository()
        assert repo.exists_by_code("house-blend") is False

        repo.add(
            Product(
                code=ProductCode("house-blend"),
                name="House Blend",
                product_type=ProductTypeCode("coffee"),
            )
        )
        assert repo.exists_by_code("house-blend") is True

    def test_list_all_returns_products_sorted_by_code(self) -> None:
        _seed_catalog()
        repo = DjangoProductRepository()
        for code in ("tea-blend", "house-blend"):
            repo.add(
                Product(
                    code=ProductCode(code),
                    name=code.title(),
                    product_type=ProductTypeCode("coffee"),
                )
            )

        assert [p.code.value for p in repo.list_all()] == ["house-blend", "tea-blend"]


class TestSetPublished:
    def test_publishes_an_existing_product(self) -> None:
        _seed_catalog()
        repo = DjangoProductRepository()
        repo.add(
            Product(
                code=ProductCode("house-blend"),
                name="House Blend",
                product_type=ProductTypeCode("coffee"),
            )
        )

        updated = repo.set_published("house-blend", True)

        assert updated.is_published is True
        assert repo.get_by_code("house-blend").is_published is True

    def test_raises_when_the_product_is_missing(self) -> None:
        # The adapter guards its own not-found path even though the use case checks
        # existence first (a direct call or a concurrent deletion can still hit it).
        with pytest.raises(ProductNotFoundError):
            DjangoProductRepository().set_published("ghost", True)


def test_value_model_str_is_informative() -> None:
    _seed_catalog("origin")
    stored = DjangoProductRepository().add(
        Product(
            code=ProductCode("house-blend"),
            name="House Blend",
            product_type=ProductTypeCode("coffee"),
            values=(_value("origin", "ethiopia"),),
        )
    )
    row = ProductAttributeValueModel.objects.get(product_id=stored.id)

    assert str(ProductModel.objects.get(code="house-blend")) == "house-blend"
    assert str(row) == f"{row.product_id}:{row.attribute_id}"
