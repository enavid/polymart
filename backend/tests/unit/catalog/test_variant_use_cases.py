"""Unit tests for the variant use cases (fakes, no Django/DB)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import ProductRepository, VariantRepository
from src.application.catalog.use_cases import (
    CreateVariant,
    CreateVariantCommand,
    GetVariant,
    ListProductVariants,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Product, ProductVariant
from src.domain.catalog.exceptions import (
    ProductNotFoundError,
    VariantAlreadyExistsError,
    VariantNotFoundError,
)
from src.domain.catalog.value_objects import ProductCode, ProductTypeCode


class FakeProductRepository(ProductRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, Product] = {}

    def seed(self, product: Product) -> None:
        product.id = len(self._by_code) + 1
        self._by_code[product.code.value] = product

    def add(self, product: Product) -> Product:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> Product:
        try:
            return self._by_code[code]
        except KeyError:
            raise ProductNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:  # pragma: no cover - unused here
        return code in self._by_code

    def list_all(self) -> list[Product]:  # pragma: no cover - unused here
        return list(self._by_code.values())


class FakeVariantRepository(VariantRepository):
    def __init__(self) -> None:
        self._by_sku: dict[str, ProductVariant] = {}
        self._sequence = 0

    def add(self, variant: ProductVariant) -> ProductVariant:
        sku = variant.sku.value
        if sku in self._by_sku:
            raise VariantAlreadyExistsError(sku)
        self._sequence += 1
        variant.id = self._sequence
        self._by_sku[sku] = variant
        return variant

    def get_by_sku(self, sku: str) -> ProductVariant:
        try:
            return self._by_sku[sku]
        except KeyError:
            raise VariantNotFoundError(sku) from None

    def exists_by_sku(self, sku: str) -> bool:
        return sku in self._by_sku

    def list_for_product(self, product_code: str) -> list[ProductVariant]:
        return [
            self._by_sku[s]
            for s in sorted(self._by_sku)
            if self._by_sku[s].product.value == product_code
        ]


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
def products() -> FakeProductRepository:
    repo = FakeProductRepository()
    repo.seed(
        Product(
            code=ProductCode("house-blend"),
            name="House Blend",
            product_type=ProductTypeCode("coffee"),
        )
    )
    return repo


@pytest.fixture
def variants() -> FakeVariantRepository:
    return FakeVariantRepository()


@pytest.fixture
def audit() -> FakeAuditRecorder:
    return FakeAuditRecorder()


def _use_case(
    variants: FakeVariantRepository,
    products: FakeProductRepository,
    audit: FakeAuditRecorder,
) -> CreateVariant:
    return CreateVariant(variants, products, audit)


def _command(**overrides: object) -> CreateVariantCommand:
    defaults: dict[str, object] = {
        "product": "house-blend",
        "sku": "coffee-250",
        "name": "250g Bag",
    }
    defaults.update(overrides)
    return CreateVariantCommand(**defaults)  # type: ignore[arg-type]


class TestCreateVariant:
    def test_persists_a_variant_with_a_canonical_sku(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        variant = _use_case(variants, products, audit).execute(_command())

        assert variant.id is not None
        assert variant.product.value == "house-blend"
        # The SKU is canonicalized to uppercase regardless of how it was supplied.
        assert variant.sku.value == "COFFEE-250"

    def test_rejects_a_variant_for_an_unknown_product(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        with pytest.raises(ProductNotFoundError):
            _use_case(variants, products, audit).execute(_command(product="ghost"))

        assert variants.list_for_product("ghost") == []

    def test_rejects_a_duplicate_sku(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        use_case = _use_case(variants, products, audit)
        use_case.execute(_command())

        with pytest.raises(VariantAlreadyExistsError):
            # Same SKU in a different case must still collide.
            use_case.execute(_command(sku="COFFEE-250", name="Another"))

    def test_writes_a_durable_audit_entry(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        variant = _use_case(variants, products, audit).execute(_command(), actor="operator")

        calls = [c for c in audit.calls if c.action == "variant.created"]
        assert len(calls) == 1
        call = calls[0]
        assert call.resource_type == "variant"
        assert call.resource_id == str(variant.id)
        assert call.actor == "operator"
        recorded = {change.field: change.after for change in call.changes}
        assert recorded["sku"] == "COFFEE-250"
        assert recorded["product"] == "house-blend"

    def test_logs_the_actor(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        with capture_logs() as logs:
            _use_case(variants, products, audit).execute(_command(), actor="operator")

        events = [e for e in logs if e["event"] == "variant_created"]
        assert events and events[0]["actor"] == "operator"


class TestReads:
    def test_get_returns_the_requested_variant(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        _use_case(variants, products, audit).execute(_command())

        assert GetVariant(variants).execute(sku="COFFEE-250").sku.value == "COFFEE-250"

    def test_get_raises_when_missing(self, variants: FakeVariantRepository) -> None:
        with pytest.raises(VariantNotFoundError):
            GetVariant(variants).execute(sku="GHOST")

    def test_list_returns_variants_for_an_existing_product(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        create = _use_case(variants, products, audit)
        create.execute(_command(sku="coffee-1000", name="1kg Bag"))
        create.execute(_command(sku="coffee-250", name="250g Bag"))

        listed = ListProductVariants(variants, products).execute(product_code="house-blend")

        assert [v.sku.value for v in listed] == ["COFFEE-1000", "COFFEE-250"]

    def test_list_raises_for_an_unknown_product(
        self,
        variants: FakeVariantRepository,
        products: FakeProductRepository,
    ) -> None:
        with pytest.raises(ProductNotFoundError):
            ListProductVariants(variants, products).execute(product_code="ghost")
