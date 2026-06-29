"""Unit tests for the category-assignment domain rule (pure Python, no DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.exceptions import DuplicateCategoryAssignmentError
from src.domain.catalog.services import reject_duplicate_categories
from src.domain.catalog.value_objects import CategorySlug


def _slugs(*values: str) -> tuple[CategorySlug, ...]:
    return tuple(CategorySlug(value) for value in values)


class TestRejectDuplicateCategories:
    def test_returns_the_assignment_unchanged_when_unique(self) -> None:
        assignment = _slugs("coffee", "espresso")

        assert reject_duplicate_categories(assignment) == assignment

    def test_accepts_an_empty_assignment(self) -> None:
        assert reject_duplicate_categories(()) == ()

    def test_preserves_order(self) -> None:
        assignment = _slugs("tea", "coffee", "espresso")

        assert reject_duplicate_categories(assignment) == assignment

    def test_rejects_a_repeated_category(self) -> None:
        with pytest.raises(DuplicateCategoryAssignmentError):
            reject_duplicate_categories(_slugs("coffee", "coffee"))
