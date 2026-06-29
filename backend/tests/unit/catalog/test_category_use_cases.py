"""Unit tests for the category use cases (fakes, no Django/DB)."""

from __future__ import annotations

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.catalog.ports import CategoryRepository
from src.application.catalog.use_cases import (
    CreateCategory,
    CreateCategoryCommand,
    GetCategory,
    ListCategories,
)
from src.domain.audit.entities import FieldChange
from src.domain.catalog.entities import Category
from src.domain.catalog.exceptions import (
    CategoryAlreadyExistsError,
    CategoryNotFoundError,
    InvalidCategorySlugError,
    ParentCategoryNotFoundError,
    SelfParentingCategoryError,
)
from src.domain.catalog.value_objects import CategorySlug


class FakeCategoryRepository(CategoryRepository):
    def __init__(self) -> None:
        self._by_slug: dict[str, Category] = {}
        self._sequence = 0

    def seed(self, category: Category) -> None:
        self._sequence += 1
        category.id = self._sequence
        self._by_slug[category.slug.value] = category

    def add(self, category: Category) -> Category:
        if category.slug.value in self._by_slug:
            raise CategoryAlreadyExistsError(category.slug.value)
        self._sequence += 1
        category.id = self._sequence
        self._by_slug[category.slug.value] = category
        return category

    def get_by_slug(self, slug: str) -> Category:
        try:
            return self._by_slug[slug]
        except KeyError:
            raise CategoryNotFoundError(slug) from None

    def exists_by_slug(self, slug: str) -> bool:
        return slug in self._by_slug

    def list_all(self) -> list[Category]:
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
def repository() -> FakeCategoryRepository:
    return FakeCategoryRepository()


@pytest.fixture
def audit() -> RecordingAudit:
    return RecordingAudit()


class TestCreateCategory:
    def test_creates_a_root_category(
        self, repository: FakeCategoryRepository, audit: RecordingAudit
    ) -> None:
        use_case = CreateCategory(repository, audit)

        category = use_case.execute(CreateCategoryCommand(slug="coffee", name="Coffee"))

        assert category.id is not None
        assert category.slug == CategorySlug("coffee")
        assert category.parent is None

    def test_creates_a_child_under_an_existing_parent(
        self, repository: FakeCategoryRepository, audit: RecordingAudit
    ) -> None:
        use_case = CreateCategory(repository, audit)
        use_case.execute(CreateCategoryCommand(slug="coffee", name="Coffee"))

        child = use_case.execute(
            CreateCategoryCommand(slug="espresso", name="Espresso", parent="coffee")
        )

        assert child.parent == CategorySlug("coffee")

    def test_records_an_audit_event_with_the_actor(
        self, repository: FakeCategoryRepository, audit: RecordingAudit
    ) -> None:
        CreateCategory(repository, audit).execute(
            CreateCategoryCommand(slug="coffee", name="Coffee"), actor="42"
        )

        assert audit.records[0]["action"] == "category.created"
        assert audit.records[0]["actor"] == "42"

    def test_logs_a_structured_creation_event(
        self, repository: FakeCategoryRepository, audit: RecordingAudit
    ) -> None:
        with capture_logs() as logs:
            CreateCategory(repository, audit).execute(
                CreateCategoryCommand(slug="coffee", name="Coffee"), actor="42"
            )

        events = [e for e in logs if e["event"] == "category_created"]
        assert events and events[0]["actor"] == "42"

    def test_rejects_a_duplicate_slug(
        self, repository: FakeCategoryRepository, audit: RecordingAudit
    ) -> None:
        use_case = CreateCategory(repository, audit)
        use_case.execute(CreateCategoryCommand(slug="coffee", name="Coffee"))

        with pytest.raises(CategoryAlreadyExistsError):
            use_case.execute(CreateCategoryCommand(slug="coffee", name="Coffee Again"))

    def test_rejects_an_unknown_parent(
        self, repository: FakeCategoryRepository, audit: RecordingAudit
    ) -> None:
        with pytest.raises(ParentCategoryNotFoundError):
            CreateCategory(repository, audit).execute(
                CreateCategoryCommand(slug="espresso", name="Espresso", parent="ghost")
            )

    def test_does_not_persist_a_category_with_an_unknown_parent(
        self, repository: FakeCategoryRepository, audit: RecordingAudit
    ) -> None:
        with pytest.raises(ParentCategoryNotFoundError):
            CreateCategory(repository, audit).execute(
                CreateCategoryCommand(slug="espresso", name="Espresso", parent="ghost")
            )

        assert not repository.exists_by_slug("espresso")
        assert audit.records == []

    def test_rejects_a_malformed_slug(
        self, repository: FakeCategoryRepository, audit: RecordingAudit
    ) -> None:
        with pytest.raises(InvalidCategorySlugError):
            CreateCategory(repository, audit).execute(
                CreateCategoryCommand(slug="Not A Slug", name="Coffee")
            )

    def test_rejects_a_self_parenting_category(
        self, repository: FakeCategoryRepository, audit: RecordingAudit
    ) -> None:
        with pytest.raises(SelfParentingCategoryError):
            CreateCategory(repository, audit).execute(
                CreateCategoryCommand(slug="coffee", name="Coffee", parent="coffee")
            )


class TestGetCategory:
    def test_returns_a_seeded_category(
        self, repository: FakeCategoryRepository
    ) -> None:
        repository.seed(Category(slug=CategorySlug("coffee"), name="Coffee"))

        category = GetCategory(repository).execute(slug="coffee")

        assert category.name == "Coffee"

    def test_raises_for_an_unknown_slug(
        self, repository: FakeCategoryRepository
    ) -> None:
        with pytest.raises(CategoryNotFoundError):
            GetCategory(repository).execute(slug="ghost")


class TestListCategories:
    def test_lists_every_category(self, repository: FakeCategoryRepository) -> None:
        repository.seed(Category(slug=CategorySlug("coffee"), name="Coffee"))
        repository.seed(Category(slug=CategorySlug("tea"), name="Tea"))

        categories = ListCategories(repository).execute()

        assert [c.slug.value for c in categories] == ["coffee", "tea"]
