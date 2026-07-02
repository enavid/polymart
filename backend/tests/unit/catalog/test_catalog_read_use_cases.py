"""Unit tests for the catalog read/publish use cases (fakes, no DB)."""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import (
    ProductFilters,
    ProductPage,
    ProductQueryRepository,
    ProductRepository,
)
from src.application.catalog.use_cases import (
    GetPublishedProduct,
    GetStorefrontProductImages,
    SearchCatalogProducts,
    SearchCatalogProductsQuery,
    SetProductPublished,
    SetProductPublishedCommand,
    SummariseStorefrontPrices,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Product
from src.domain.catalog.exceptions import (
    InvalidPaginationError,
    ProductNotFoundError,
)
from src.domain.catalog.value_objects import ProductCode, ProductTypeCode


def _product(code: str, *, published: bool = True) -> Product:
    return Product(
        code=ProductCode(code),
        name=code.replace("-", " ").title(),
        product_type=ProductTypeCode("coffee"),
        is_published=published,
    )


class FakeProductRepository(ProductRepository):
    """Only the methods the publish use case needs are exercised here."""

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

    def set_published(self, code: str, is_published: bool) -> Product:
        product = self.get_by_code(code)
        product.is_published = is_published
        return product


class FakeProductQueryRepository(ProductQueryRepository):
    """Records the filters/pagination it was asked for and returns canned products."""

    def __init__(self, products: list[Product]) -> None:
        self._products = products
        self.last_filters: ProductFilters | None = None
        self.last_limit: int | None = None
        self.last_offset: int | None = None
        self.summaries_result: dict[str, object] = {}
        self.last_summary_call: tuple[tuple[str, ...], str] | None = None
        self.images_result: dict[str, object] = {}
        self.last_images_call: tuple[str, ...] | None = None

    def search(self, *, filters: ProductFilters, limit: int, offset: int) -> ProductPage:
        self.last_filters = filters
        self.last_limit = limit
        self.last_offset = offset
        window = self._products[offset : offset + limit]
        return ProductPage(items=tuple(window), total=len(self._products))

    def get_published_by_code(self, code: str) -> Product:
        for product in self._products:
            if product.code.value == code and product.is_published:
                return product
        raise ProductNotFoundError(code)

    def price_summaries(self, *, codes, channel):
        self.last_summary_call = (tuple(codes), channel)
        return self.summaries_result

    def primary_images(self, *, codes):
        self.last_images_call = tuple(codes)
        return self.images_result


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


class TestSearchCatalogProducts:
    def test_returns_a_page_with_the_total_count(self) -> None:
        repo = FakeProductQueryRepository([_product("a"), _product("b"), _product("c")])

        page = SearchCatalogProducts(repo).execute(SearchCatalogProductsQuery(limit=2, offset=0))

        assert [p.code.value for p in page.items] == ["a", "b"]
        assert page.total == 3

    def test_always_restricts_to_published_products(self) -> None:
        # The storefront search must never expose drafts: published_only is forced on,
        # not taken from the caller.
        repo = FakeProductQueryRepository([_product("a")])

        SearchCatalogProducts(repo).execute(SearchCatalogProductsQuery())

        assert repo.last_filters is not None
        assert repo.last_filters.published_only is True

    def test_passes_every_filter_through_to_the_repository(self) -> None:
        repo = FakeProductQueryRepository([_product("a")])

        SearchCatalogProducts(repo).execute(
            SearchCatalogProductsQuery(
                search="house",
                category="beverages",
                collection="featured",
                product_type="coffee",
            )
        )

        f = repo.last_filters
        assert f is not None
        assert (f.search, f.category, f.collection, f.product_type) == (
            "house",
            "beverages",
            "featured",
            "coffee",
        )

    def test_applies_the_default_window_when_unspecified(self) -> None:
        repo = FakeProductQueryRepository([_product("a")])

        SearchCatalogProducts(repo).execute(SearchCatalogProductsQuery())

        assert repo.last_limit == 20 and repo.last_offset == 0

    def test_logs_a_structured_search_event(self) -> None:
        repo = FakeProductQueryRepository([_product("a"), _product("b")])

        with capture_logs() as logs:
            SearchCatalogProducts(repo).execute(SearchCatalogProductsQuery(search="a"))

        events = [e for e in logs if e["event"] == "catalog_products_searched"]
        assert events and events[0]["count"] == 2

    @pytest.mark.parametrize("limit", [0, -1, 101])
    def test_rejects_an_out_of_range_limit(self, limit: int) -> None:
        repo = FakeProductQueryRepository([])

        with pytest.raises(InvalidPaginationError):
            SearchCatalogProducts(repo).execute(SearchCatalogProductsQuery(limit=limit))

    def test_rejects_a_negative_offset(self) -> None:
        repo = FakeProductQueryRepository([])

        with pytest.raises(InvalidPaginationError):
            SearchCatalogProducts(repo).execute(SearchCatalogProductsQuery(offset=-1))


class TestGetPublishedProduct:
    def test_returns_a_published_product(self) -> None:
        repo = FakeProductQueryRepository([_product("house-blend", published=True)])

        product = GetPublishedProduct(repo).execute(code="house-blend")

        assert product.code.value == "house-blend"

    def test_an_unpublished_product_is_not_found(self) -> None:
        # A draft must be indistinguishable from a missing product (no existence leak).
        repo = FakeProductQueryRepository([_product("draft", published=False)])

        with pytest.raises(ProductNotFoundError):
            GetPublishedProduct(repo).execute(code="draft")

    def test_an_unknown_product_is_not_found(self) -> None:
        repo = FakeProductQueryRepository([])

        with pytest.raises(ProductNotFoundError):
            GetPublishedProduct(repo).execute(code="ghost")


class TestSetProductPublished:
    def test_publishes_a_product(self) -> None:
        products = FakeProductRepository()
        products.seed(_product("house-blend", published=False))
        audit = RecordingAudit()

        result = SetProductPublished(products, audit).execute(
            SetProductPublishedCommand(product="house-blend", is_published=True)
        )

        assert result.is_published is True

    def test_records_an_audit_event_with_before_and_after(self) -> None:
        products = FakeProductRepository()
        products.seed(_product("house-blend", published=False))
        audit = RecordingAudit()

        SetProductPublished(products, audit).execute(
            SetProductPublishedCommand(product="house-blend", is_published=True), actor="42"
        )

        record = audit.records[-1]
        assert record["action"] == "product.publish_changed"
        assert record["resource_type"] == "product"
        assert record["actor"] == "42"
        change = record["changes"][0]
        assert change.field == "is_published"
        assert change.before is False
        assert change.after is True

    def test_logs_a_structured_event(self) -> None:
        products = FakeProductRepository()
        products.seed(_product("house-blend", published=False))
        audit = RecordingAudit()

        with capture_logs() as logs:
            SetProductPublished(products, audit).execute(
                SetProductPublishedCommand(product="house-blend", is_published=True), actor="42"
            )

        events = [e for e in logs if e["event"] == "product_publish_changed"]
        assert events and events[0]["actor"] == "42" and events[0]["is_published"] is True

    def test_unknown_product_raises_not_found(self) -> None:
        products = FakeProductRepository()
        audit = RecordingAudit()

        with pytest.raises(ProductNotFoundError):
            SetProductPublished(products, audit).execute(
                SetProductPublishedCommand(product="ghost", is_published=True)
            )

        assert audit.records == []


class TestSummariseStorefrontPrices:
    def test_returns_empty_without_calling_the_repo_for_no_codes(self) -> None:
        repo = FakeProductQueryRepository([])

        result = SummariseStorefrontPrices(repo).execute(codes=[], channel="ir-main")

        assert result == {}
        assert repo.last_summary_call is None

    def test_delegates_codes_and_channel_to_the_repo(self) -> None:
        repo = FakeProductQueryRepository([])
        repo.summaries_result = {"house-blend": object()}

        result = SummariseStorefrontPrices(repo).execute(codes=["house-blend"], channel="ir-main")

        assert result == repo.summaries_result
        assert repo.last_summary_call == (("house-blend",), "ir-main")


class TestGetStorefrontProductImages:
    def test_returns_empty_without_calling_the_repo_for_no_codes(self) -> None:
        repo = FakeProductQueryRepository([])

        result = GetStorefrontProductImages(repo).execute(codes=[])

        assert result == {}
        assert repo.last_images_call is None

    def test_delegates_codes_to_the_repo(self) -> None:
        repo = FakeProductQueryRepository([])
        repo.images_result = {"house-blend": object()}

        result = GetStorefrontProductImages(repo).execute(codes=["house-blend", "espresso"])

        assert result == repo.images_result
        assert repo.last_images_call == ("house-blend", "espresso")
