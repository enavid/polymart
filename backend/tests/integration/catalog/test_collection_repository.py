"""Integration tests for the Django collection repository (real DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.entities import Collection
from src.domain.catalog.exceptions import (
    CollectionAlreadyExistsError,
    CollectionNotFoundError,
)
from src.domain.catalog.value_objects import CollectionSlug
from src.infrastructure.catalog.models import CollectionModel
from src.infrastructure.catalog.repositories import DjangoCollectionRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _collection(slug: str, name: str) -> Collection:
    return Collection(slug=CollectionSlug(slug), name=name)


class TestAdd:
    def test_persists_a_collection(self) -> None:
        repo = DjangoCollectionRepository()

        stored = repo.add(_collection("featured", "Featured"))

        assert stored.id is not None
        assert stored.slug == CollectionSlug("featured")

    def test_rejects_a_duplicate_slug(self) -> None:
        repo = DjangoCollectionRepository()
        repo.add(_collection("featured", "Featured"))

        with pytest.raises(CollectionAlreadyExistsError):
            repo.add(_collection("featured", "Featured Again"))


class TestGetBySlug:
    def test_returns_a_persisted_collection(self) -> None:
        repo = DjangoCollectionRepository()
        repo.add(_collection("featured", "Featured"))

        collection = repo.get_by_slug("featured")

        assert collection.name == "Featured"

    def test_raises_for_an_unknown_slug(self) -> None:
        with pytest.raises(CollectionNotFoundError):
            DjangoCollectionRepository().get_by_slug("ghost")


class TestExistsBySlug:
    def test_reports_presence(self) -> None:
        repo = DjangoCollectionRepository()
        repo.add(_collection("featured", "Featured"))

        assert repo.exists_by_slug("featured")
        assert not repo.exists_by_slug("ghost")


class TestListAll:
    def test_lists_collections_sorted_by_slug(self) -> None:
        repo = DjangoCollectionRepository()
        repo.add(_collection("featured", "Featured"))
        repo.add(_collection("clearance", "Clearance"))

        collections = repo.list_all()

        assert [c.slug.value for c in collections] == ["clearance", "featured"]


def test_collection_model_str_is_the_slug() -> None:
    DjangoCollectionRepository().add(_collection("featured", "Featured"))

    assert str(CollectionModel.objects.get(slug="featured")) == "featured"
