"""Unit tests for the variant value objects (pure domain, no Django)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.domain.catalog.exceptions import InvalidMediaAssetError, InvalidSkuError
from src.domain.catalog.value_objects import MediaAsset, Sku


class TestSku:
    def test_accepts_an_uppercase_stock_keeping_code(self) -> None:
        assert Sku("COFFEE-250").value == "COFFEE-250"

    def test_canonicalizes_to_uppercase(self) -> None:
        # A SKU is a single stock-keeping identity; case must not split it in two.
        assert Sku("coffee-250").value == "COFFEE-250"

    def test_trims_surrounding_whitespace(self) -> None:
        assert Sku("  coffee-250  ").value == "COFFEE-250"

    def test_str_is_the_code(self) -> None:
        assert str(Sku("coffee-250")) == "COFFEE-250"

    @pytest.mark.parametrize(
        "raw",
        ["", "  ", "has space", "trailing-", "-leading", "under_score", "dot.dot", "A" * 65],
    )
    def test_rejects_malformed_codes(self, raw: str) -> None:
        with pytest.raises(InvalidSkuError):
            Sku(raw)

    def test_is_immutable(self) -> None:
        with pytest.raises(FrozenInstanceError):
            Sku("coffee-250").value = "tea"  # type: ignore[misc]


class TestMediaAsset:
    @pytest.mark.parametrize(
        "url",
        ["https://cdn.example.com/a.jpg", "http://x/y.png", "/media/coffee/250g.webp"],
    )
    def test_accepts_an_absolute_or_site_relative_url(self, url: str) -> None:
        assert MediaAsset(url=url).url == url

    def test_trims_url_and_alt_text(self) -> None:
        asset = MediaAsset(url="  /media/a.jpg  ", alt_text="  250g bag  ")

        assert asset.url == "/media/a.jpg"
        assert asset.alt_text == "250g bag"

    def test_alt_text_defaults_to_empty(self) -> None:
        assert MediaAsset(url="/media/a.jpg").alt_text == ""

    @pytest.mark.parametrize(
        "url",
        ["", "   ", "ftp://x/y", "example.com/a.jpg", "has space.jpg", "a" * 2049],
    )
    def test_rejects_a_malformed_url(self, url: str) -> None:
        with pytest.raises(InvalidMediaAssetError):
            MediaAsset(url=url)

    def test_rejects_overlong_alt_text(self) -> None:
        with pytest.raises(InvalidMediaAssetError):
            MediaAsset(url="/media/a.jpg", alt_text="x" * 256)

    def test_is_immutable(self) -> None:
        with pytest.raises(FrozenInstanceError):
            MediaAsset(url="/media/a.jpg").url = "/other.jpg"  # type: ignore[misc]
