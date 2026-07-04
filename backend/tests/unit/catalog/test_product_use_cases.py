"""Unit tests for the product use cases (fakes, no Django/DB)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import (
    AttributeRepository,
    ProductCategoryRepository,
    ProductRepository,
    ProductTypeRepository,
)
from src.application.catalog.use_cases import (
    AttributeValueInput,
    CreateProduct,
    CreateProductCommand,
    GetProduct,
    ListProducts,
    ListProductsWithCategories,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Attribute, Product, ProductType
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeNotFoundError,
    MissingRequiredAttributeError,
    ProductAlreadyExistsError,
    ProductNotFoundError,
    ProductTypeNotFoundError,
)
from src.domain.catalog.value_objects import AttributeCode, CategorySlug, ProductTypeCode


class FakeAttributeRepository(AttributeRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, Attribute] = {}

    def seed(self, attribute: Attribute) -> None:
        attribute.id = len(self._by_code) + 1
        self._by_code[attribute.code.value] = attribute

    def add(self, attribute: Attribute) -> Attribute:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> Attribute:
        try:
            return self._by_code[code]
        except KeyError:
            raise AttributeNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:
        return code in self._by_code

    def list_all(self) -> list[Attribute]:  # pragma: no cover - unused here
        return list(self._by_code.values())


class FakeProductTypeRepository(ProductTypeRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, ProductType] = {}

    def seed(self, product_type: ProductType) -> None:
        product_type.id = len(self._by_code) + 1
        self._by_code[product_type.code.value] = product_type

    def add(self, product_type: ProductType) -> ProductType:  # pragma: no cover - unused
        raise NotImplementedError

    def get_by_code(self, code: str) -> ProductType:
        try:
            return self._by_code[code]
        except KeyError:
            raise ProductTypeNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:
        return code in self._by_code

    def list_all(self) -> list[ProductType]:  # pragma: no cover - unused here
        return list(self._by_code.values())


class FakeProductRepository(ProductRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, Product] = {}
        self._sequence = 0

    def add(self, product: Product) -> Product:
        code = product.code.value
        if code in self._by_code:
            raise ProductAlreadyExistsError(code)
        self._sequence += 1
        product.id = self._sequence
        self._by_code[code] = product
        return product

    def get_by_code(self, code: str) -> Product:
        try:
            return self._by_code[code]
        except KeyError:
            raise ProductNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:
        return code in self._by_code

    def list_all(self) -> list[Product]:
        return [self._by_code[c] for c in sorted(self._by_code)]

    def set_published(  # pragma: no cover - unused here
        self, code: str, is_published: bool
    ) -> Product:
        raise NotImplementedError


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
    repo = FakeAttributeRepository()
    repo.seed(
        Attribute(
            code=AttributeCode("origin"),
            name="Origin",
            input_type=AttributeInputType.PLAIN_TEXT,
        )
    )
    repo.seed(
        Attribute(
            code=AttributeCode("weight"),
            name="Weight",
            input_type=AttributeInputType.NUMBER,
            required=True,
        )
    )
    return repo


@pytest.fixture
def product_types() -> FakeProductTypeRepository:
    repo = FakeProductTypeRepository()
    repo.seed(
        ProductType(
            code=ProductTypeCode("coffee"),
            name="Coffee",
            attributes=(AttributeCode("origin"), AttributeCode("weight")),
        )
    )
    return repo


@pytest.fixture
def products() -> FakeProductRepository:
    return FakeProductRepository()


@pytest.fixture
def audit() -> FakeAuditRecorder:
    return FakeAuditRecorder()


def _use_case(
    products: FakeProductRepository,
    product_types: FakeProductTypeRepository,
    attributes: FakeAttributeRepository,
    audit: FakeAuditRecorder,
) -> CreateProduct:
    return CreateProduct(products, product_types, attributes, audit)


def _command(**overrides: object) -> CreateProductCommand:
    defaults: dict[str, object] = {
        "code": "house-blend",
        "name": "House Blend",
        "product_type": "coffee",
        "values": (
            AttributeValueInput(attribute="origin", value="ethiopia"),
            AttributeValueInput(attribute="weight", value="250"),
        ),
    }
    defaults.update(overrides)
    return CreateProductCommand(**defaults)  # type: ignore[arg-type]


class TestCreateProduct:
    def test_persists_a_conforming_product(
        self,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        product = _use_case(products, product_types, attributes, audit).execute(_command())

        assert product.id is not None
        assert product.code.value == "house-blend"
        assert {v.attribute.value: v.value for v in product.values} == {
            "origin": "ethiopia",
            "weight": "250",
        }

    def test_carries_metadata(
        self,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        product = _use_case(products, product_types, attributes, audit).execute(
            _command(metadata={"sku-supplier": "ACME-1"})
        )

        assert product.metadata == {"sku-supplier": "ACME-1"}

    def test_rejects_an_unknown_product_type(
        self,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        with pytest.raises(ProductTypeNotFoundError):
            _use_case(products, product_types, attributes, audit).execute(
                _command(product_type="ghost", values=())
            )

        assert products.list_all() == []

    def test_propagates_a_conformance_failure(
        self,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        # "weight" is required by the coffee type but omitted here.
        with pytest.raises(MissingRequiredAttributeError):
            _use_case(products, product_types, attributes, audit).execute(
                _command(values=(AttributeValueInput(attribute="origin", value="ethiopia"),))
            )

        assert products.list_all() == []

    def test_rejects_a_duplicate_code(
        self,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        use_case = _use_case(products, product_types, attributes, audit)
        use_case.execute(_command())

        with pytest.raises(ProductAlreadyExistsError):
            use_case.execute(_command(name="House Blend Again"))

    def test_writes_a_durable_audit_entry(
        self,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        product = _use_case(products, product_types, attributes, audit).execute(
            _command(), actor="operator"
        )

        calls = [c for c in audit.calls if c.action == "product.created"]
        assert len(calls) == 1
        call = calls[0]
        assert call.resource_type == "product"
        assert call.resource_id == str(product.id)
        assert call.actor == "operator"
        recorded = {change.field: change.after for change in call.changes}
        assert recorded["code"] == "house-blend"
        assert recorded["product_type"] == "coffee"
        assert recorded["value_count"] == 2

    def test_logs_the_actor(
        self,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        with capture_logs() as logs:
            _use_case(products, product_types, attributes, audit).execute(
                _command(), actor="operator"
            )

        events = [e for e in logs if e["event"] == "product_created"]
        assert events and events[0]["actor"] == "operator"


class TestReads:
    def test_get_returns_the_requested_product(
        self,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        _use_case(products, product_types, attributes, audit).execute(_command())

        assert GetProduct(products).execute(code="house-blend").code.value == "house-blend"

    def test_get_raises_when_missing(self, products: FakeProductRepository) -> None:
        with pytest.raises(ProductNotFoundError):
            GetProduct(products).execute(code="ghost")

    def test_list_returns_products_sorted_by_code(
        self,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        create = _use_case(products, product_types, attributes, audit)
        create.execute(_command(code="tea-blend", name="Tea Blend"))
        create.execute(_command(code="house-blend", name="House Blend"))

        assert [p.code.value for p in ListProducts(products).execute()] == [
            "house-blend",
            "tea-blend",
        ]

    def test_list_with_categories_attaches_each_products_membership(
        self,
        products: FakeProductRepository,
        product_types: FakeProductTypeRepository,
        attributes: FakeAttributeRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        create = _use_case(products, product_types, attributes, audit)
        create.execute(_command(code="house-blend", name="House Blend"))
        create.execute(_command(code="tea-blend", name="Tea Blend"))
        categories = FakeProductCategoryRepository()
        categories.replace("house-blend", [CategorySlug("hot-drinks"), CategorySlug("beans")])

        result = ListProductsWithCategories(products, categories).execute()

        # Products keep their code-sorted order, each carrying its own membership
        # (empty tuple when a product has no categories) in one batched read.
        assert [(row.product.code.value, [c.value for c in row.categories]) for row in result] == [
            ("house-blend", ["hot-drinks", "beans"]),
            ("tea-blend", []),
        ]


class FakeProductCategoryRepository(ProductCategoryRepository):
    def __init__(self) -> None:
        self._by_product: dict[str, tuple[CategorySlug, ...]] = {}

    def replace(
        self, product_code: str, categories: Sequence[CategorySlug]
    ) -> tuple[CategorySlug, ...]:
        stored = tuple(categories)
        self._by_product[product_code] = stored
        return stored

    def list_for_product(self, product_code: str) -> tuple[CategorySlug, ...]:
        return self._by_product.get(product_code, ())
