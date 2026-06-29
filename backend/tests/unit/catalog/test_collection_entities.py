"""Unit tests for the Collection entity (pure Python, no DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Collection
from src.domain.catalog.exceptions import InvalidCollectionNameError
from src.domain.catalog.value_objects import CollectionSlug


def _collection(slug: str = "featured", name: str = "Featured") -> Collection:
    return Collection(slug=CollectionSlug(slug), name=name)


class TestCollection:
    def test_carries_a_slug_and_name(self) -> None:
        collection = _collection()
        assert collection.slug == CollectionSlug("featured")
        assert collection.name == "Featured"

    def test_a_new_collection_has_no_identity_yet(self) -> None:
        assert _collection().id is None

    def test_trims_the_display_name(self) -> None:
        assert _collection(name="  Featured  ").name == "Featured"

    @pytest.mark.parametrize("raw", ["", "   ", "x" * 256])
    def test_rejects_a_blank_or_overlong_name(self, raw: str) -> None:
        with pytest.raises(InvalidCollectionNameError):
            _collection(name=raw)
