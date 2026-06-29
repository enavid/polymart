"""Unit tests for the money/price value objects (pure domain, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.catalog.exceptions import (
    InvalidChannelReferenceError,
    InvalidMoneyError,
)
from src.domain.catalog.value_objects import ChannelPrice, Money


class TestMoney:
    def test_accepts_a_positive_decimal_amount(self) -> None:
        money = Money(amount=Decimal("1500.00"), currency="IRR")

        assert money.amount == Decimal("1500.00")
        assert money.currency == "IRR"

    def test_normalizes_the_currency_to_upper_case(self) -> None:
        assert Money(amount=Decimal("10"), currency=" usd ").currency == "USD"

    def test_rejects_a_float_amount(self) -> None:
        # Money must never be built from a binary float: that is the whole point of
        # using Decimal for money (no 0.1 + 0.2 == 0.30000000000000004 surprises).
        with pytest.raises(InvalidMoneyError):
            Money(amount=1500.00, currency="IRR")  # type: ignore[arg-type]

    def test_rejects_an_integer_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=1500, currency="IRR")  # type: ignore[arg-type]

    def test_rejects_a_zero_amount(self) -> None:
        # A base price is the list price of a sellable unit; zero is a promotion
        # concern (a later phase), not a base price.
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("0"), currency="IRR")

    def test_rejects_a_negative_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("-1"), currency="IRR")

    @pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
    def test_rejects_a_non_finite_amount(self, raw: str) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal(raw), currency="IRR")

    def test_rejects_too_many_decimal_places(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1.23456"), currency="USD")

    def test_accepts_the_maximum_decimal_places(self) -> None:
        assert Money(amount=Decimal("1.2345"), currency="USD").amount == Decimal("1.2345")

    def test_rejects_too_many_digits(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("1234567890123456789"), currency="IRR")

    @pytest.mark.parametrize("code", ["US", "USDX", "12$", "", "ir r"])
    def test_rejects_a_malformed_currency(self, code: str) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(amount=Decimal("10"), currency=code)

    def test_is_immutable(self) -> None:
        money = Money(amount=Decimal("10"), currency="IRR")
        with pytest.raises(Exception):  # noqa: B017 - frozen dataclass raises FrozenInstanceError
            money.amount = Decimal("20")  # type: ignore[misc]

    def test_equality_is_by_value(self) -> None:
        assert Money(amount=Decimal("10.00"), currency="IRR") == Money(
            amount=Decimal("10.00"), currency="IRR"
        )


class TestChannelPrice:
    def test_pairs_a_channel_with_money(self) -> None:
        price = ChannelPrice(channel="ir-toman", money=Money(Decimal("10"), "IRR"))

        assert price.channel == "ir-toman"
        assert price.money.currency == "IRR"

    def test_strips_the_channel_reference(self) -> None:
        assert ChannelPrice(channel="  ir-toman ", money=Money(Decimal("10"), "IRR")).channel == (
            "ir-toman"
        )

    def test_rejects_a_blank_channel_reference(self) -> None:
        with pytest.raises(InvalidChannelReferenceError):
            ChannelPrice(channel="   ", money=Money(Decimal("10"), "IRR"))

    def test_rejects_an_overlong_channel_reference(self) -> None:
        with pytest.raises(InvalidChannelReferenceError):
            ChannelPrice(channel="x" * 65, money=Money(Decimal("10"), "IRR"))
