"""Unit tests for the Category entity (pure Python, no DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Category
from src.domain.catalog.exceptions import (
    InvalidCategoryNameError,
    SelfParentingCategoryError,
)
from src.domain.catalog.value_objects import CategorySlug


def _category(slug: str = "coffee", name: str = "Coffee", parent: str | None = None) -> Category:
    return Category(
        slug=CategorySlug(slug),
        name=name,
        parent=CategorySlug(parent) if parent is not None else None,
    )


class TestCategory:
    def test_a_root_category_has_no_parent(self) -> None:
        category = _category()
        assert category.parent is None

    def test_a_child_references_its_parent_by_slug(self) -> None:
        category = _category(slug="espresso", name="Espresso", parent="coffee")
        assert category.parent == CategorySlug("coffee")

    def test_trims_the_display_name(self) -> None:
        assert _category(name="  Coffee  ").name == "Coffee"

    @pytest.mark.parametrize("raw", ["", "   ", "x" * 256])
    def test_rejects_a_blank_or_overlong_name(self, raw: str) -> None:
        with pytest.raises(InvalidCategoryNameError):
            _category(name=raw)

    def test_rejects_a_category_that_is_its_own_parent(self) -> None:
        with pytest.raises(SelfParentingCategoryError):
            _category(slug="coffee", parent="coffee")
