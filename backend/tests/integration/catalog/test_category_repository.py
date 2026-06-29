"""Integration tests for the Django category repository (real DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Category
from src.domain.catalog.exceptions import (
    CategoryAlreadyExistsError,
    CategoryNotFoundError,
    ParentCategoryNotFoundError,
)
from src.domain.catalog.value_objects import CategorySlug
from src.infrastructure.catalog.models import CategoryModel
from src.infrastructure.catalog.repositories import DjangoCategoryRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _category(slug: str, name: str, parent: str | None = None) -> Category:
    return Category(
        slug=CategorySlug(slug),
        name=name,
        parent=CategorySlug(parent) if parent is not None else None,
    )


class TestAdd:
    def test_persists_a_root_category(self) -> None:
        repo = DjangoCategoryRepository()

        stored = repo.add(_category("coffee", "Coffee"))

        assert stored.id is not None
        assert stored.slug == CategorySlug("coffee")
        assert stored.parent is None

    def test_persists_a_child_category(self) -> None:
        repo = DjangoCategoryRepository()
        repo.add(_category("coffee", "Coffee"))

        stored = repo.add(_category("espresso", "Espresso", parent="coffee"))

        assert stored.parent == CategorySlug("coffee")

    def test_rejects_a_duplicate_slug(self) -> None:
        repo = DjangoCategoryRepository()
        repo.add(_category("coffee", "Coffee"))

        with pytest.raises(CategoryAlreadyExistsError):
            repo.add(_category("coffee", "Coffee Again"))

    def test_raises_if_the_parent_vanished_before_insert(self) -> None:
        # Defends the create use case's check-then-act window: the parent was
        # validated, then deleted concurrently before this insert.
        repo = DjangoCategoryRepository()

        with pytest.raises(ParentCategoryNotFoundError):
            repo.add(_category("espresso", "Espresso", parent="ghost"))

        assert not CategoryModel.objects.filter(slug="espresso").exists()


class TestGetBySlug:
    def test_returns_a_persisted_category_with_its_parent(self) -> None:
        repo = DjangoCategoryRepository()
        repo.add(_category("coffee", "Coffee"))
        repo.add(_category("espresso", "Espresso", parent="coffee"))

        category = repo.get_by_slug("espresso")

        assert category.name == "Espresso"
        assert category.parent == CategorySlug("coffee")

    def test_raises_for_an_unknown_slug(self) -> None:
        with pytest.raises(CategoryNotFoundError):
            DjangoCategoryRepository().get_by_slug("ghost")


class TestExistsBySlug:
    def test_reports_presence(self) -> None:
        repo = DjangoCategoryRepository()
        repo.add(_category("coffee", "Coffee"))

        assert repo.exists_by_slug("coffee")
        assert not repo.exists_by_slug("ghost")


class TestListAll:
    def test_lists_categories_sorted_by_slug(self) -> None:
        repo = DjangoCategoryRepository()
        repo.add(_category("tea", "Tea"))
        repo.add(_category("coffee", "Coffee"))

        categories = repo.list_all()

        assert [c.slug.value for c in categories] == ["coffee", "tea"]


def test_category_model_str_is_the_slug() -> None:
    DjangoCategoryRepository().add(_category("coffee", "Coffee"))

    assert str(CategoryModel.objects.get(slug="coffee")) == "coffee"
