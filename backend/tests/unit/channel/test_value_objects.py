"""Unit tests for the channel value objects.

These guard the domain invariants with no framework and no database. The cases
are deliberately adversarial: currency and slug parsing is the first line of
defence for a money-handling system, so the edges must be pinned down.
"""
from __future__ import annotations

import pytest

from src.domain.channel.exceptions import InvalidChannelSlugError, InvalidCurrencyCodeError
from src.domain.channel.value_objects import ChannelSlug, Currency


class TestCurrency:
    def test_accepts_a_valid_iso_like_code(self) -> None:
        assert Currency("IRR").code == "IRR"

    def test_strips_surrounding_whitespace(self) -> None:
        assert Currency("  USD  ").code == "USD"

    def test_is_an_immutable_value_object(self) -> None:
        currency = Currency("IRR")
        with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises
            currency.code = "USD"  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert Currency("IRR") == Currency("IRR")
        assert Currency("IRR") != Currency("USD")

    def test_str_returns_the_code(self) -> None:
        assert str(Currency("IRR")) == "IRR"

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "ir",  # too short
            "irrr",  # too long
            "irr",  # lower case is not accepted
            "Irr",  # mixed case
            "IR1",  # digits not allowed
            "I R",  # internal whitespace
            "€UR",  # non-ascii
        ],
    )
    def test_rejects_malformed_codes(self, raw: str) -> None:
        with pytest.raises(InvalidCurrencyCodeError):
            Currency(raw)


class TestChannelSlug:
    @pytest.mark.parametrize(
        "raw",
        ["coffee", "auto-parts", "shop2", "a-b-c", "x1-y2-z3"],
    )
    def test_accepts_valid_slugs(self, raw: str) -> None:
        assert ChannelSlug(raw).value == raw

    def test_strips_surrounding_whitespace(self) -> None:
        assert ChannelSlug("  coffee  ").value == "coffee"

    def test_is_immutable(self) -> None:
        slug = ChannelSlug("coffee")
        with pytest.raises(Exception):  # noqa: B017
            slug.value = "tea"  # type: ignore[misc]

    def test_str_returns_the_raw_value(self) -> None:
        assert str(ChannelSlug("auto-parts")) == "auto-parts"

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "Coffee",  # upper case
            "auto parts",  # space
            "-coffee",  # leading hyphen
            "coffee-",  # trailing hyphen
            "auto--parts",  # consecutive hyphens
            "under_score",  # underscore
            "قهوه",  # non-ascii
            "a" * 65,  # exceeds max length
        ],
    )
    def test_rejects_malformed_slugs(self, raw: str) -> None:
        with pytest.raises(InvalidChannelSlugError):
            ChannelSlug(raw)
