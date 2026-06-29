"""Unit tests for the price-uniqueness domain service (pure domain, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.catalog.exceptions import DuplicateChannelPriceError
from src.domain.catalog.services import reject_duplicate_channel_prices
from src.domain.catalog.value_objects import ChannelPrice, Money


def _price(channel: str, amount: str, currency: str = "IRR") -> ChannelPrice:
    return ChannelPrice(channel=channel, money=Money(amount=Decimal(amount), currency=currency))


def test_returns_the_prices_unchanged_when_each_channel_is_distinct() -> None:
    prices = (_price("ir-toman", "1500"), _price("us-store", "10", "USD"))

    assert reject_duplicate_channel_prices(prices) == prices


def test_rejects_two_prices_for_the_same_channel() -> None:
    # A variant has at most one base price per channel; a repeated channel is a
    # malformed request, not a silently last-wins overwrite.
    with pytest.raises(DuplicateChannelPriceError):
        reject_duplicate_channel_prices((_price("ir-toman", "1500"), _price("ir-toman", "1600")))


def test_an_empty_set_of_prices_is_allowed() -> None:
    assert reject_duplicate_channel_prices(()) == ()
