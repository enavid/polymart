"""Unit tests for the catalog CSV import/export use cases (fakes, no DB)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog import use_cases as uc
from src.application.catalog.ports import (
    AttributeRepository,
    CatalogImportWriter,
    CategoryRepository,
    ProductCategoryRepository,
    ProductImportItem,
    ProductRepository,
    ProductTypeRepository,
)
from src.application.catalog.use_cases import (
    AttributeValueInput,
    ExportCatalogProducts,
    ImportCatalogProducts,
    ProductRow,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Attribute, Product, ProductType
from src.domain.catalog.enums import AttributeInputType
from src.domain.catalog.exceptions import (
    AttributeNotFoundError,
    ImportTooLargeError,
    ProductTypeNotFoundError,
)
from src.domain.catalog.value_objects import (
    AttributeCode,
    AttributeValue,
    CategorySlug,
    ProductCode,
    ProductTypeCode,
)


class FakeProductRepository(ProductRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, Product] = {}

    def seed(self, *products: Product) -> None:
        for product in products:
            product.id = len(self._by_code) + 1
            self._by_code[product.code.value] = product

    def add(self, product: Product) -> Product:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> Product:  # pragma: no cover - unused here
        raise NotImplementedError

    def exists_by_code(self, code: str) -> bool:
        return code in self._by_code

    def list_all(self) -> list[Product]:
        return list(self._by_code.values())

    def set_published(  # pragma: no cover - unused here
        self, code: str, is_published: bool
    ) -> Product:
        raise NotImplementedError


class FakeProductTypeRepository(ProductTypeRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, ProductType] = {}

    def seed(self, product_type: ProductType) -> None:
        self._by_code[product_type.code.value] = product_type

    def add(self, product_type: ProductType) -> ProductType:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> ProductType:
        try:
            return self._by_code[code]
        except KeyError:
            raise ProductTypeNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:  # pragma: no cover - unused here
        return code in self._by_code

    def list_all(self) -> list[ProductType]:  # pragma: no cover - unused here
        raise NotImplementedError


class FakeAttributeRepository(AttributeRepository):
    def __init__(self) -> None:
        self._by_code: dict[str, Attribute] = {}

    def seed(self, attribute: Attribute) -> None:
        self._by_code[attribute.code.value] = attribute

    def add(self, attribute: Attribute) -> Attribute:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> Attribute:
        try:
            return self._by_code[code]
        except KeyError:
            raise AttributeNotFoundError(code) from None

    def exists_by_code(self, code: str) -> bool:  # pragma: no cover - unused here
        return code in self._by_code

    def list_all(self) -> list[Attribute]:  # pragma: no cover - unused here
        raise NotImplementedError


class FakeCategoryRepository(CategoryRepository):
    def __init__(self) -> None:
        self._slugs: set[str] = set()

    def seed(self, *slugs: str) -> None:
        self._slugs.update(slugs)

    def add(self, category: object) -> object:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_slug(self, slug: str) -> object:  # pragma: no cover - unused here
        raise NotImplementedError

    def exists_by_slug(self, slug: str) -> bool:
        return slug in self._slugs

    def list_all(self) -> list[object]:  # pragma: no cover - unused here
        raise NotImplementedError


class FakeProductCategoryRepository(ProductCategoryRepository):
    def __init__(self) -> None:
        self._by_product: dict[str, tuple[CategorySlug, ...]] = {}

    def seed(self, product_code: str, *slugs: str) -> None:
        self._by_product[product_code] = tuple(CategorySlug(slug) for slug in slugs)

    def replace(  # pragma: no cover - unused here
        self, product_code: str, categories: Sequence[CategorySlug]
    ) -> tuple[CategorySlug, ...]:
        raise NotImplementedError

    def list_for_product(self, product_code: str) -> tuple[CategorySlug, ...]:
        return self._by_product.get(product_code, ())


class FakeCatalogImportWriter(CatalogImportWriter):
    def __init__(self) -> None:
        self.items: list[ProductImportItem] | None = None

    def create_products(self, items: Sequence[ProductImportItem]) -> None:
        self.items = list(items)


class RecordingAudit(AuditRecorder):
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None,
        changes: tuple[FieldChange, ...],
    ) -> None:
        self.records.append(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "actor": actor,
                "changes": changes,
            }
        )


def _coffee_type(*attributes: str) -> ProductType:
    return ProductType(
        code=ProductTypeCode("coffee"),
        name="Coffee",
        attributes=tuple(AttributeCode(code) for code in attributes),
    )


def _required_text(code: str) -> Attribute:
    return Attribute(
        code=AttributeCode(code),
        name=code.title(),
        input_type=AttributeInputType.PLAIN_TEXT,
        required=True,
    )


def _row(
    code: str,
    *,
    product_type: str = "coffee",
    categories: tuple[str, ...] = (),
    values: tuple[AttributeValueInput, ...] = (),
    is_published: bool = False,
) -> ProductRow:
    return ProductRow(
        code=code,
        name=code.title(),
        product_type=product_type,
        is_published=is_published,
        categories=categories,
        values=values,
    )


@pytest.fixture
def products() -> FakeProductRepository:
    return FakeProductRepository()


@pytest.fixture
def product_types() -> FakeProductTypeRepository:
    repo = FakeProductTypeRepository()
    repo.seed(_coffee_type())
    return repo


@pytest.fixture
def attributes() -> FakeAttributeRepository:
    return FakeAttributeRepository()


@pytest.fixture
def categories() -> FakeCategoryRepository:
    repo = FakeCategoryRepository()
    repo.seed("espresso", "decaf")
    return repo


@pytest.fixture
def writer() -> FakeCatalogImportWriter:
    return FakeCatalogImportWriter()


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


def _import_use_case(
    products: FakeProductRepository,
    product_types: FakeProductTypeRepository,
    attributes: FakeAttributeRepository,
    categories: FakeCategoryRepository,
    writer: FakeCatalogImportWriter,
    audit: RecordingAudit,
) -> ImportCatalogProducts:
    return ImportCatalogProducts(products, product_types, attributes, categories, writer, audit)


class TestImportCatalogProducts:
    def test_imports_new_products(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)

        result = use_case.execute([_row("house-blend"), _row("cold-brew")])

        assert result.created == 2
        assert result.errors == ()
        assert writer.items is not None
        assert [item.product.code.value for item in writer.items] == ["house-blend", "cold-brew"]

    def test_assigns_categories(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)

        use_case.execute([_row("house-blend", categories=("espresso", "decaf"))])

        assert writer.items is not None
        assert [c.value for c in writer.items[0].categories] == ["espresso", "decaf"]

    def test_collects_errors_and_writes_nothing(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)
        bad = _row("ghost", product_type="missing-type")

        result = use_case.execute([_row("house-blend"), bad])

        assert result.created == 0
        assert len(result.errors) == 1
        assert result.errors[0].row_number == 2
        assert result.errors[0].code == "ghost"
        assert "product type not found" in result.errors[0].error
        assert writer.items is None  # all-or-nothing: nothing persisted

    def test_reports_each_failing_row(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)
        bad_type = _row("a", product_type="ghost")
        bad_category = _row("b", categories=("unknown",))

        result = use_case.execute([bad_type, bad_category])

        assert [(e.row_number, e.code) for e in result.errors] == [(1, "a"), (2, "b")]

    def test_rejects_a_duplicate_code_within_the_file(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)

        result = use_case.execute([_row("house-blend"), _row("house-blend")])

        assert result.created == 0
        assert len(result.errors) == 1
        assert result.errors[0].row_number == 2
        assert "duplicate product code in import" in result.errors[0].error

    def test_rejects_a_code_that_already_exists(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        products.seed(
            Product(
                code=ProductCode("house-blend"),
                name="House Blend",
                product_type=ProductTypeCode("coffee"),
            )
        )
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)

        result = use_case.execute([_row("house-blend")])

        assert result.created == 0
        assert "already exists" in result.errors[0].error

    def test_rejects_an_unknown_category(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)

        result = use_case.execute([_row("house-blend", categories=("unknown",))])

        assert "unknown category" in result.errors[0].error

    def test_rejects_a_malformed_code(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)

        result = use_case.execute([_row("Not A Code")])

        assert result.created == 0
        assert "invalid product code" in result.errors[0].error

    def test_enforces_attribute_conformance(
        self, products, attributes, categories, writer, audit
    ) -> None:
        # A product type with a required attribute; a row that omits it must fail.
        types = FakeProductTypeRepository()
        types.seed(_coffee_type("origin"))
        attributes.seed(_required_text("origin"))
        use_case = _import_use_case(products, types, attributes, categories, writer, audit)

        result = use_case.execute([_row("house-blend")])

        assert "missing required attribute" in result.errors[0].error

    def test_normalizes_conforming_values(
        self, products, attributes, categories, writer, audit
    ) -> None:
        types = FakeProductTypeRepository()
        types.seed(_coffee_type("origin"))
        attributes.seed(_required_text("origin"))
        use_case = _import_use_case(products, types, attributes, categories, writer, audit)

        values = (AttributeValueInput(attribute="origin", value="ethiopia"),)
        use_case.execute([_row("house-blend", values=values)])

        assert writer.items is not None
        item = writer.items[0]
        assert [(v.attribute.value, v.value) for v in item.product.values] == [
            ("origin", "ethiopia")
        ]

    def test_rejects_a_file_larger_than_the_cap(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)
        too_many = [_row(f"p{i}") for i in range(uc._MAX_IMPORT_ROWS + 1)]

        with pytest.raises(ImportTooLargeError):
            use_case.execute(too_many)

    def test_records_an_audit_summary_and_logs(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)

        with capture_logs() as logs:
            use_case.execute([_row("house-blend"), _row("cold-brew")], actor="42")

        record = audit.records[-1]
        assert record["action"] == "catalog.products_imported"
        assert record["actor"] == "42"
        assert record["changes"][0].after == 2
        events = [e for e in logs if e["event"] == "catalog_products_imported"]
        assert events and events[0]["actor"] == "42" and events[0]["created"] == 2

    def test_does_not_audit_when_a_row_is_invalid(
        self, products, product_types, attributes, categories, writer, audit
    ) -> None:
        use_case = _import_use_case(products, product_types, attributes, categories, writer, audit)

        use_case.execute([_row("house-blend", categories=("unknown",))])

        assert audit.records == []


class TestExportCatalogProducts:
    def test_exports_products_with_categories_and_values(self) -> None:
        products = FakeProductRepository()
        products.seed(
            Product(
                code=ProductCode("house-blend"),
                name="House Blend",
                product_type=ProductTypeCode("coffee"),
                values=(AttributeValue(attribute=AttributeCode("origin"), value="ethiopia"),),
                is_published=True,
            ),
            Product(
                code=ProductCode("cold-brew"),
                name="Cold Brew",
                product_type=ProductTypeCode("coffee"),
            ),
        )
        product_categories = FakeProductCategoryRepository()
        product_categories.seed("house-blend", "espresso", "decaf")

        rows = ExportCatalogProducts(products, product_categories).execute()

        first = rows[0]
        assert first.code == "house-blend"
        assert first.is_published is True
        assert first.categories == ("espresso", "decaf")
        assert [(v.attribute, v.value) for v in first.values] == [("origin", "ethiopia")]
        assert rows[1].code == "cold-brew"
        assert rows[1].categories == ()

    def test_exports_nothing_when_there_are_no_products(self) -> None:
        rows = ExportCatalogProducts(
            FakeProductRepository(), FakeProductCategoryRepository()
        ).execute()

        assert rows == ()
