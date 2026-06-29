"""Unit tests for the collection-membership domain rule (pure Python, no DB)."""

from __future__ import annotations

import pytest

from src.domain.catalog.exceptions import DuplicateProductMembershipError
from src.domain.catalog.services import reject_duplicate_products
from src.domain.catalog.value_objects import ProductCode


def _codes(*values: str) -> tuple[ProductCode, ...]:
    return tuple(ProductCode(value) for value in values)


class TestRejectDuplicateProducts:
    def test_returns_the_membership_unchanged_when_unique(self) -> None:
        membership = _codes("house-blend", "cold-brew")

        assert reject_duplicate_products(membership) == membership

    def test_accepts_an_empty_membership(self) -> None:
        assert reject_duplicate_products(()) == ()

    def test_preserves_order(self) -> None:
        membership = _codes("cold-brew", "house-blend", "espresso-shot")

        assert reject_duplicate_products(membership) == membership

    def test_rejects_a_repeated_product(self) -> None:
        with pytest.raises(DuplicateProductMembershipError):
            reject_duplicate_products(_codes("house-blend", "house-blend"))
