"""Unit tests for the product-type use cases (fakes, no Django/DB)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import AttributeRepository, ProductTypeRepository
from src.application.catalog.use_cases import (
    CreateAttribute,
    CreateAttributeCommand,
    CreateProductType,
    CreateProductTypeCommand,
    GetProductType,
    ListProductTypes,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Attribute, ProductType
from src.domain.catalog.exceptions import (
    AttributeAlreadyExistsError,
    AttributeNotFoundError,
    DuplicateAttributeAssignmentError,
    ProductTypeAlreadyExistsError,
    ProductTypeNotFoundError,
    UnknownAttributeError,
)


class FakeAttributeRepository(AttributeRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, Attribute] = {}
        self._sequence = 0

    def add(self, attribute: Attribute) -> Attribute:
        code = attribute.code.value
        if code in self._by_code:
            raise AttributeAlreadyExistsError(code)
        self._sequence += 1
        attribute.id = self._sequence
        self._by_code[code] = attribute
        return attribute

    def get_by_code(self, code: str) -> Attribute:
        try:
            return self._by_code[code]
        except KeyError:
            raise AttributeNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:
        return code in self._by_code

    def list_all(self) -> list[Attribute]:
        return [self._by_code[c] for c in sorted(self._by_code)]


class FakeProductTypeRepository(ProductTypeRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, ProductType] = {}
        self._sequence = 0

    def add(self, product_type: ProductType) -> ProductType:
        code = product_type.code.value
        if code in self._by_code:
            raise ProductTypeAlreadyExistsError(code)
        self._sequence += 1
        product_type.id = self._sequence
        self._by_code[code] = product_type
        return product_type

    def get_by_code(self, code: str) -> ProductType:
        try:
            return self._by_code[code]
        except KeyError:
            raise ProductTypeNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:
        return code in self._by_code

    def list_all(self) -> list[ProductType]:
        return [self._by_code[c] for c in sorted(self._by_code)]


class RecordedAudit:
    def __init__(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None,
        changes: tuple[FieldChange, ...],
    ) -> None:
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.actor = actor
        self.changes = changes


class FakeAuditRecorder(AuditRecorder):
    def __init__(self) -> None:
        self.calls: list[RecordedAudit] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: Sequence[FieldChange] = (),
    ) -> None:
        self.calls.append(RecordedAudit(action, resource_type, resource_id, actor, tuple(changes)))


@pytest.fixture
def attributes() -> FakeAttributeRepository:
    return FakeAttributeRepository()


@pytest.fixture
def product_types() -> FakeProductTypeRepository:
    return FakeProductTypeRepository()


@pytest.fixture
def audit() -> FakeAuditRecorder:
    return FakeAuditRecorder()


def _seed_attribute(repo: FakeAttributeRepository, audit: FakeAuditRecorder, code: str) -> None:
    CreateAttribute(repo, audit).execute(
        CreateAttributeCommand(code=code, name=code.title(), input_type="plain_text")
    )


class TestCreateProductType:
    def test_persists_with_its_attribute_references_in_order(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        _seed_attribute(attributes, audit, "roast-level")
        _seed_attribute(attributes, audit, "origin")

        product_type = CreateProductType(product_types, attributes, audit).execute(
            CreateProductTypeCommand(
                code="coffee", name="Coffee", attributes=("roast-level", "origin")
            )
        )

        assert product_type.id is not None
        assert [a.value for a in product_type.attributes] == ["roast-level", "origin"]

    def test_allows_a_type_with_no_attributes(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        product_type = CreateProductType(product_types, attributes, audit).execute(
            CreateProductTypeCommand(code="misc", name="Misc")
        )

        assert product_type.attributes == ()

    def test_rejects_an_unknown_attribute_reference(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        # "origin" exists; "ghost" does not.
        _seed_attribute(attributes, audit, "origin")

        with pytest.raises(UnknownAttributeError):
            CreateProductType(product_types, attributes, audit).execute(
                CreateProductTypeCommand(
                    code="coffee", name="Coffee", attributes=("origin", "ghost")
                )
            )

        assert product_types.list_all() == []

    def test_rejects_a_duplicate_attribute_reference(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        _seed_attribute(attributes, audit, "origin")

        with pytest.raises(DuplicateAttributeAssignmentError):
            CreateProductType(product_types, attributes, audit).execute(
                CreateProductTypeCommand(
                    code="coffee", name="Coffee", attributes=("origin", "origin")
                )
            )

    def test_persists_variant_attributes_in_order(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        _seed_attribute(attributes, audit, "origin")
        _seed_attribute(attributes, audit, "weight")
        _seed_attribute(attributes, audit, "grind")

        product_type = CreateProductType(product_types, attributes, audit).execute(
            CreateProductTypeCommand(
                code="coffee",
                name="Coffee",
                attributes=("origin",),
                variant_attributes=("weight", "grind"),
            )
        )

        assert [a.value for a in product_type.attributes] == ["origin"]
        assert [a.value for a in product_type.variant_attributes] == ["weight", "grind"]

    def test_rejects_an_unknown_variant_attribute_reference(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        _seed_attribute(attributes, audit, "origin")

        with pytest.raises(UnknownAttributeError):
            CreateProductType(product_types, attributes, audit).execute(
                CreateProductTypeCommand(
                    code="coffee",
                    name="Coffee",
                    attributes=("origin",),
                    variant_attributes=("ghost",),
                )
            )

        assert product_types.list_all() == []

    def test_rejects_an_attribute_assigned_to_both_levels(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        _seed_attribute(attributes, audit, "origin")

        with pytest.raises(DuplicateAttributeAssignmentError):
            CreateProductType(product_types, attributes, audit).execute(
                CreateProductTypeCommand(
                    code="coffee",
                    name="Coffee",
                    attributes=("origin",),
                    variant_attributes=("origin",),
                )
            )

    def test_audit_entry_counts_both_attribute_levels(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        _seed_attribute(attributes, audit, "origin")
        _seed_attribute(attributes, audit, "weight")

        CreateProductType(product_types, attributes, audit).execute(
            CreateProductTypeCommand(
                code="coffee",
                name="Coffee",
                attributes=("origin",),
                variant_attributes=("weight",),
            ),
            actor="operator",
        )

        call = next(c for c in audit.calls if c.action == "product_type.created")
        recorded = {change.field: change.after for change in call.changes}
        assert recorded["attribute_count"] == 1
        assert recorded["variant_attribute_count"] == 1

    def test_rejects_a_duplicate_code(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        use_case = CreateProductType(product_types, attributes, audit)
        use_case.execute(CreateProductTypeCommand(code="coffee", name="Coffee"))

        with pytest.raises(ProductTypeAlreadyExistsError):
            use_case.execute(CreateProductTypeCommand(code="coffee", name="Coffee Again"))

    def test_writes_a_durable_audit_entry(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        _seed_attribute(attributes, audit, "origin")

        product_type = CreateProductType(product_types, attributes, audit).execute(
            CreateProductTypeCommand(code="coffee", name="Coffee", attributes=("origin",)),
            actor="operator",
        )

        type_calls = [c for c in audit.calls if c.action == "product_type.created"]
        assert len(type_calls) == 1
        call = type_calls[0]
        assert call.resource_type == "product_type"
        assert call.resource_id == str(product_type.id)
        assert call.actor == "operator"
        recorded = {change.field: change.after for change in call.changes}
        assert recorded["code"] == "coffee"
        assert recorded["attribute_count"] == 1

    def test_logs_the_actor(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        with capture_logs() as logs:
            CreateProductType(product_types, attributes, audit).execute(
                CreateProductTypeCommand(code="coffee", name="Coffee"), actor="operator"
            )

        events = [e for e in logs if e["event"] == "product_type_created"]
        assert events and events[0]["actor"] == "operator"


class TestReads:
    def test_get_returns_the_requested_type(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        CreateProductType(product_types, attributes, audit).execute(
            CreateProductTypeCommand(code="coffee", name="Coffee")
        )

        assert GetProductType(product_types).execute(code="coffee").code.value == "coffee"

    def test_get_raises_when_missing(self, product_types: FakeProductTypeRepository) -> None:
        with pytest.raises(ProductTypeNotFoundError):
            GetProductType(product_types).execute(code="ghost")

    def test_list_returns_types_sorted_by_code(
        self,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        create = CreateProductType(product_types, attributes, audit)
        create.execute(CreateProductTypeCommand(code="tea", name="Tea"))
        create.execute(CreateProductTypeCommand(code="coffee", name="Coffee"))

        assert [t.code.value for t in ListProductTypes(product_types).execute()] == [
            "coffee",
            "tea",
        ]
