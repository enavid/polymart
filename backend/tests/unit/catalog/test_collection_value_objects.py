"""Unit tests for the catalog collection value objects (pure Python, no DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.exceptions import InvalidCollectionSlugError
from src.domain.catalog.value_objects import CollectionSlug


class TestCollectionSlug:
    def test_accepts_a_kebab_case_slug(self) -> None:
        assert CollectionSlug("summer-sale").value == "summer-sale"

    def test_trims_surrounding_whitespace(self) -> None:
        assert CollectionSlug("  featured  ").value == "featured"

    def test_is_value_equal(self) -> None:
        assert CollectionSlug("featured") == CollectionSlug("featured")

    def test_str_is_the_slug(self) -> None:
        assert str(CollectionSlug("featured")) == "featured"

    @pytest.mark.parametrize(
        "raw",
        ["", "  ", "Featured", "summer sale", "summer_sale", "-featured", "featured-", "x" * 65],
    )
    def test_rejects_a_malformed_slug(self, raw: str) -> None:
        with pytest.raises(InvalidCollectionSlugError):
            CollectionSlug(raw)
