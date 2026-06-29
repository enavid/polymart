"""Unit tests for the collection use cases (fakes, no Django/DB)."""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import CollectionRepository
from src.application.catalog.use_cases import (
    CreateCollection,
    CreateCollectionCommand,
    GetCollection,
    ListCollections,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Collection
from src.domain.catalog.exceptions import (
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
    InvalidCollectionSlugError,
)
from src.domain.catalog.value_objects import CollectionSlug


class FakeCollectionRepository(CollectionRepository):
    def __init__(self) -> None:
        self._by_slug: dict[str, Collection] = {}
        self._sequence = 0

    def seed(self, collection: Collection) -> None:
        self._sequence += 1
        collection.id = self._sequence
        self._by_slug[collection.slug.value] = collection

    def add(self, collection: Collection) -> Collection:
        if collection.slug.value in self._by_slug:
            raise CollectionAlreadyExistsError(collection.slug.value)
        self._sequence += 1
        collection.id = self._sequence
        self._by_slug[collection.slug.value] = collection
        return collection

    def get_by_slug(self, slug: str) -> Collection:
        try:
            return self._by_slug[slug]
        except KeyError:
            raise CollectionNotFoundError(slug) from None

    def exists_by_slug(self, slug: str) -> bool:
        return slug in self._by_slug

    def list_all(self) -> list[Collection]:
        return [self._by_slug[s] for s in sorted(self._by_slug)]


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


@pytest.fixture
def repository() -> FakeCollectionRepository:
    return FakeCollectionRepository()


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


class TestCreateCollection:
    def test_creates_a_collection(
        self, repository: FakeCollectionRepository, audit: RecordingAudit
    ) -> None:
        use_case = CreateCollection(repository, audit)

        collection = use_case.execute(CreateCollectionCommand(slug="featured", name="Featured"))

        assert collection.id is not None
        assert collection.slug == CollectionSlug("featured")

    def test_records_an_audit_event_with_the_actor(
        self, repository: FakeCollectionRepository, audit: RecordingAudit
    ) -> None:
        CreateCollection(repository, audit).execute(
            CreateCollectionCommand(slug="featured", name="Featured"), actor="42"
        )

        assert audit.records[0]["action"] == "collection.created"
        assert audit.records[0]["actor"] == "42"

    def test_logs_a_structured_creation_event(
        self, repository: FakeCollectionRepository, audit: RecordingAudit
    ) -> None:
        with capture_logs() as logs:
            CreateCollection(repository, audit).execute(
                CreateCollectionCommand(slug="featured", name="Featured"), actor="42"
            )

        events = [e for e in logs if e["event"] == "collection_created"]
        assert events and events[0]["actor"] == "42"

    def test_rejects_a_duplicate_slug(
        self, repository: FakeCollectionRepository, audit: RecordingAudit
    ) -> None:
        use_case = CreateCollection(repository, audit)
        use_case.execute(CreateCollectionCommand(slug="featured", name="Featured"))

        with pytest.raises(CollectionAlreadyExistsError):
            use_case.execute(CreateCollectionCommand(slug="featured", name="Featured Again"))

    def test_rejects_a_malformed_slug(
        self, repository: FakeCollectionRepository, audit: RecordingAudit
    ) -> None:
        with pytest.raises(InvalidCollectionSlugError):
            CreateCollection(repository, audit).execute(
                CreateCollectionCommand(slug="Not A Slug", name="Featured")
            )


class TestGetCollection:
    def test_returns_a_seeded_collection(self, repository: FakeCollectionRepository) -> None:
        repository.seed(Collection(slug=CollectionSlug("featured"), name="Featured"))

        collection = GetCollection(repository).execute(slug="featured")

        assert collection.name == "Featured"

    def test_raises_for_an_unknown_slug(self, repository: FakeCollectionRepository) -> None:
        with pytest.raises(CollectionNotFoundError):
            GetCollection(repository).execute(slug="ghost")


class TestListCollections:
    def test_lists_every_collection(self, repository: FakeCollectionRepository) -> None:
        repository.seed(Collection(slug=CollectionSlug("featured"), name="Featured"))
        repository.seed(Collection(slug=CollectionSlug("clearance"), name="Clearance"))

        collections = ListCollections(repository).execute()

        assert [c.slug.value for c in collections] == ["clearance", "featured"]
