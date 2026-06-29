"""Unit tests for the collection-membership use cases (fakes, no DB)."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import (
    CollectionProductRepository,
    CollectionRepository,
    ProductRepository,
)
from src.application.catalog.use_cases import (
    GetCollectionProducts,
    SetCollectionProducts,
    SetCollectionProductsCommand,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Collection, Product
from src.domain.catalog.exceptions import (
    CollectionNotFoundError,
    DuplicateProductMembershipError,
    InvalidProductCodeError,
    UnknownProductError,
)
from src.domain.catalog.value_objects import CollectionSlug, ProductCode


class FakeCollectionRepository(CollectionRepository):
    def __init__(self) -> None:
        self._by_slug: dict[str, Collection] = {}

    def seed(self, collection: Collection) -> None:
        collection.id = len(self._by_slug) + 1
        self._by_slug[collection.slug.value] = collection

    def add(self, collection: Collection) -> Collection:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_slug(self, slug: str) -> Collection:
        try:
            return self._by_slug[slug]
        except KeyError:
            raise CollectionNotFoundError(slug) from None

    def exists_by_slug(self, slug: str) -> bool:  # pragma: no cover - unused here
        return slug in self._by_slug

    def list_all(self) -> list[Collection]:  # pragma: no cover - unused here
        return list(self._by_slug.values())


class FakeProductRepository(ProductRepository):
    def __init__(self) -> None:
        self._codes: set[str] = set()

    def seed(self, *codes: str) -> None:
        self._codes.update(codes)

    def add(self, product: Product) -> Product:  # pragma: no cover - unused here
        raise NotImplementedError

    def get_by_code(self, code: str) -> Product:  # pragma: no cover - unused here
        raise NotImplementedError

    def exists_by_code(self, code: str) -> bool:
        return code in self._codes

    def list_all(self) -> list[Product]:  # pragma: no cover - unused here
        raise NotImplementedError


class FakeCollectionProductRepository(CollectionProductRepository):
    def __init__(self) -> None:
        self._by_collection: dict[str, tuple[ProductCode, ...]] = {}

    def replace(
        self, collection_slug: str, products: Sequence[ProductCode]
    ) -> tuple[ProductCode, ...]:
        stored = tuple(products)
        self._by_collection[collection_slug] = stored
        return stored

    def list_for_collection(self, collection_slug: str) -> tuple[ProductCode, ...]:
        return self._by_collection.get(collection_slug, ())


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


def _collection(slug: str = "featured") -> Collection:
    return Collection(slug=CollectionSlug(slug), name=slug.title())


@pytest.fixture
def collections() -> FakeCollectionRepository:
    repo = FakeCollectionRepository()
    repo.seed(_collection())
    return repo


@pytest.fixture
def products() -> FakeProductRepository:
    repo = FakeProductRepository()
    repo.seed("house-blend", "cold-brew")
    return repo


@pytest.fixture
def membership() -> FakeCollectionProductRepository:
    return FakeCollectionProductRepository()


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


def _set_use_case(
    membership: FakeCollectionProductRepository,
    collections: FakeCollectionRepository,
    products: FakeProductRepository,
    audit: RecordingAudit,
) -> SetCollectionProducts:
    return SetCollectionProducts(membership, collections, products, audit)


class TestSetCollectionProducts:
    def test_assigns_products_to_a_collection(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(membership, collections, products, audit)

        result = use_case.execute(
            SetCollectionProductsCommand(
                collection="featured", products=("house-blend", "cold-brew")
            )
        )

        assert [p.value for p in result] == ["house-blend", "cold-brew"]

    def test_replacing_with_an_empty_list_clears_membership(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(membership, collections, products, audit)
        use_case.execute(
            SetCollectionProductsCommand(collection="featured", products=("house-blend",))
        )

        result = use_case.execute(
            SetCollectionProductsCommand(collection="featured", products=())
        )

        assert result == ()

    def test_records_an_audit_event_with_before_and_after(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(membership, collections, products, audit)
        use_case.execute(
            SetCollectionProductsCommand(collection="featured", products=("house-blend",))
        )

        use_case.execute(
            SetCollectionProductsCommand(
                collection="featured", products=("house-blend", "cold-brew")
            ),
            actor="42",
        )

        record = audit.records[-1]
        assert record["action"] == "collection.products_changed"
        assert record["resource_type"] == "collection"
        assert record["actor"] == "42"
        change = record["changes"][0]
        assert change.before == "house-blend"
        assert change.after == "house-blend,cold-brew"

    def test_logs_a_structured_event(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(membership, collections, products, audit)

        with capture_logs() as logs:
            use_case.execute(
                SetCollectionProductsCommand(collection="featured", products=("house-blend",)),
                actor="42",
            )

        events = [e for e in logs if e["event"] == "collection_products_set"]
        assert events and events[0]["actor"] == "42" and events[0]["count"] == 1

    def test_unknown_collection_raises_not_found(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(membership, collections, products, audit)

        with pytest.raises(CollectionNotFoundError):
            use_case.execute(
                SetCollectionProductsCommand(collection="ghost", products=("house-blend",))
            )

    def test_unknown_product_raises_unknown_product(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(membership, collections, products, audit)

        with pytest.raises(UnknownProductError):
            use_case.execute(
                SetCollectionProductsCommand(collection="featured", products=("ghost",))
            )

    def test_does_not_persist_or_audit_when_a_product_is_unknown(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(membership, collections, products, audit)

        with pytest.raises(UnknownProductError):
            use_case.execute(
                SetCollectionProductsCommand(collection="featured", products=("ghost",))
            )

        assert membership.list_for_collection("featured") == ()
        assert audit.records == []

    def test_rejects_a_duplicate_product(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(membership, collections, products, audit)

        with pytest.raises(DuplicateProductMembershipError):
            use_case.execute(
                SetCollectionProductsCommand(
                    collection="featured", products=("house-blend", "house-blend")
                )
            )

    def test_rejects_a_malformed_product_code(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        use_case = _set_use_case(membership, collections, products, audit)

        with pytest.raises(InvalidProductCodeError):
            use_case.execute(
                SetCollectionProductsCommand(collection="featured", products=("Not A Code",))
            )


class TestGetCollectionProducts:
    def test_returns_the_membership(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
        products: FakeProductRepository,
        audit: RecordingAudit,
    ) -> None:
        _set_use_case(membership, collections, products, audit).execute(
            SetCollectionProductsCommand(collection="featured", products=("house-blend",))
        )

        result = GetCollectionProducts(membership, collections).execute(collection_slug="featured")

        assert [p.value for p in result] == ["house-blend"]

    def test_unknown_collection_raises_not_found(
        self,
        membership: FakeCollectionProductRepository,
        collections: FakeCollectionRepository,
    ) -> None:
        with pytest.raises(CollectionNotFoundError):
            GetCollectionProducts(membership, collections).execute(collection_slug="ghost")
