"""Unit tests for the catalog category value objects (pure Python, no DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.exceptions import InvalidCategorySlugError
from src.domain.catalog.value_objects import CategorySlug


class TestCategorySlug:
    def test_accepts_a_kebab_case_slug(self) -> None:
        assert CategorySlug("hot-drinks").value == "hot-drinks"

    def test_trims_surrounding_whitespace(self) -> None:
        assert CategorySlug("  coffee  ").value == "coffee"

    def test_is_value_equal(self) -> None:
        assert CategorySlug("coffee") == CategorySlug("coffee")

    def test_str_is_the_slug(self) -> None:
        assert str(CategorySlug("coffee")) == "coffee"

    @pytest.mark.parametrize(
        "raw",
        ["", "  ", "Coffee", "hot drinks", "hot_drinks", "-coffee", "coffee-", "x" * 65],
    )
    def test_rejects_a_malformed_slug(self, raw: str) -> None:
        with pytest.raises(InvalidCategorySlugError):
            CategorySlug(raw)
