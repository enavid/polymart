"""Unit tests for the product-category assignment use cases (fakes, no DB)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import (
    CategoryRepository,
    ProductCategoryRepository,
    ProductRepository,
)
from src.application.catalog.use_cases import (
    GetProductCategories,
    SetProductCategories,
    SetProductCategoriesCommand,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Category, Product
from src.domain.catalog.exceptions import (
    DuplicateCategoryAssignmentError,
    InvalidCategorySlugError,
    ProductNotFoundError,
    UnknownCategoryError,
)
from src.domain.catalog.value_objects import (
    CategorySlug,
    ProductCode,
    ProductTypeCode,
)


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

    def set_published(  # pragma: no cover - unused here
        self, code: str, is_published: bool
    ) -> Product:
        raise NotImplementedError


class FakeCategoryRepository(CategoryRepository):
    def __init__(self) -> None:
        self._slugs: set[str] = set()

    def seed(self, *slugs: str) -> None:
        self._slugs.update(slugs)

    def add(self, category: Category) -> Category:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_slug(self, slug: str) -> Category:  # pragma: no cover - unused here
        raise NotImplementedError

    def exists_by_slug(self, slug: str) -> bool:
        return slug in self._slugs

    def list_all(self) -> list[Category]:  # pragma: no cover - unused here
        raise NotImplementedError


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


def _product(code: str = "house-blend") -> Product:
    return Product(
        code=ProductCode(code), name=code.title(), product_type=ProductTypeCode("coffee")
    )


@pytest.fixture
def products() -> FakeProductRepository:
    repo = FakeProductRepository()
    repo.seed(_product())
    return repo


@pytest.fixture
def categories() -> FakeCategoryRepository:
    repo = FakeCategoryRepository()
    repo.seed("coffee", "espresso")
    return repo


@pytest.fixture
def assignments() -> FakeProductCategoryRepository:
    return FakeProductCategoryRepository()


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


def _set_use_case(
    assignments: FakeProductCategoryRepository,
    products: FakeProductRepository,
    categories: FakeCategoryRepository,
    audit: RecordingAudit,
) -> SetProductCategories:
    return SetProductCategories(assignments, products, categories, audit)


class TestSetProductCategories:
    def test_assigns_categories_to_a_product(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
        categories: FakeCategoryRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(assignments, products, categories, audit)

        result = use_case.execute(
            SetProductCategoriesCommand(product="house-blend", categories=("coffee", "espresso"))
        )

        assert [c.value for c in result] == ["coffee", "espresso"]

    def test_replacing_with_an_empty_set_clears_membership(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
        categories: FakeCategoryRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(assignments, products, categories, audit)
        use_case.execute(SetProductCategoriesCommand(product="house-blend", categories=("coffee",)))

        result = use_case.execute(SetProductCategoriesCommand(product="house-blend", categories=()))

        assert result == ()

    def test_records_an_audit_event_with_before_and_after(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
        categories: FakeCategoryRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(assignments, products, categories, audit)
        use_case.execute(SetProductCategoriesCommand(product="house-blend", categories=("coffee",)))

        use_case.execute(
            SetProductCategoriesCommand(product="house-blend", categories=("coffee", "espresso")),
            actor="42",
        )

        record = audit.records[-1]
        assert record["action"] == "product.categories_changed"
        assert record["actor"] == "42"
        change = record["changes"][0]
        assert change.before == "coffee"
        assert change.after == "coffee,espresso"

    def test_logs_a_structured_event(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
        categories: FakeCategoryRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(assignments, products, categories, audit)

        with capture_logs() as logs:
            use_case.execute(
                SetProductCategoriesCommand(product="house-blend", categories=("coffee",)),
                actor="42",
            )

        events = [e for e in logs if e["event"] == "product_categories_set"]
        assert events and events[0]["actor"] == "42" and events[0]["count"] == 1

    def test_unknown_product_raises_not_found(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
        categories: FakeCategoryRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(assignments, products, categories, audit)

        with pytest.raises(ProductNotFoundError):
            use_case.execute(SetProductCategoriesCommand(product="ghost", categories=("coffee",)))

    def test_unknown_category_raises_unknown_category(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
        categories: FakeCategoryRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(assignments, products, categories, audit)

        with pytest.raises(UnknownCategoryError):
            use_case.execute(
                SetProductCategoriesCommand(product="house-blend", categories=("ghost",))
            )

    def test_does_not_persist_or_audit_when_a_category_is_unknown(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
        categories: FakeCategoryRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(assignments, products, categories, audit)

        with pytest.raises(UnknownCategoryError):
            use_case.execute(
                SetProductCategoriesCommand(product="house-blend", categories=("ghost",))
            )

        assert assignments.list_for_product("house-blend") == ()
        assert audit.records == []

    def test_rejects_a_duplicate_category(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
        categories: FakeCategoryRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(assignments, products, categories, audit)

        with pytest.raises(DuplicateCategoryAssignmentError):
            use_case.execute(
                SetProductCategoriesCommand(product="house-blend", categories=("coffee", "coffee"))
            )

    def test_rejects_a_malformed_category_slug(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
        categories: FakeCategoryRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(assignments, products, categories, audit)

        with pytest.raises(InvalidCategorySlugError):
            use_case.execute(
                SetProductCategoriesCommand(product="house-blend", categories=("Not A Slug",))
            )


class TestGetProductCategories:
    def test_returns_the_membership(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
        categories: FakeCategoryRepository,
        audit: RecordingAudit,
    ) -> None:
        _set_use_case(assignments, products, categories, audit).execute(
            SetProductCategoriesCommand(product="house-blend", categories=("coffee",))
        )

        result = GetProductCategories(assignments, products).execute(product_code="house-blend")

        assert [c.value for c in result] == ["coffee"]

    def test_unknown_product_raises_not_found(
        self,
        assignments: FakeProductCategoryRepository,
        products: FakeProductRepository,
    ) -> None:
        with pytest.raises(ProductNotFoundError):
            GetProductCategories(assignments, products).execute(product_code="ghost")
