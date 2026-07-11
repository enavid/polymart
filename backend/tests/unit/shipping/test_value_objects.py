"""Unit tests for the shipping value objects (pure Python, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.shipping.exceptions import (
    InvalidDestinationError,
    InvalidMoneyError,
    InvalidShippingMethodCodeError,
    InvalidShippingZoneCodeError,
    InvalidZonedRateError,
)
from src.domain.shipping.value_objects import (
    Destination,
    Money,
    ShippingMethodCode,
    ShippingZoneCode,
    ZonedRate,
)


class TestShippingMethodCode:
    def test_normalizes_to_lower_case(self) -> None:
        assert ShippingMethodCode("Standard").value == "standard"

    def test_accepts_kebab_case(self) -> None:
        assert ShippingMethodCode("in-person").value == "in-person"

    @pytest.mark.parametrize("bad", ["", "  ", "has space", "under_score", "a" * 33, "bad!"])
    def test_rejects_malformed_codes(self, bad: str) -> None:
        with pytest.raises(InvalidShippingMethodCodeError):
            ShippingMethodCode(bad)

    def test_equality_is_by_value(self) -> None:
        assert ShippingMethodCode("EXPRESS") == ShippingMethodCode("express")

    def test_str_is_the_value(self) -> None:
        assert str(ShippingMethodCode("standard")) == "standard"


class TestMoney:
    def test_a_zero_price_is_valid(self) -> None:
        # A free shipping method priced at zero is legitimate.
        assert Money(Decimal("0"), "IRR").amount == Decimal("0")

    def test_normalizes_currency(self) -> None:
        assert Money(Decimal("50000"), "irr").currency == "IRR"

    def test_rejects_a_float_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(50000.0, "IRR")  # type: ignore[arg-type]

    def test_rejects_a_negative_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("-1"), "IRR")

    def test_rejects_too_many_decimal_places(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("1.00001"), "IRR")

    def test_rejects_a_non_finite_amount(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("NaN"), "IRR")

    def test_rejects_too_many_digits(self) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("1" * 19), "IRR")

    @pytest.mark.parametrize("bad", ["IR", "IRRR", "12R", ""])
    def test_rejects_a_malformed_currency(self, bad: str) -> None:
        with pytest.raises(InvalidMoneyError):
            Money(Decimal("1"), bad)


class TestShippingZoneCode:
    def test_normalizes_to_lower_case(self) -> None:
        assert ShippingZoneCode("Tehran").value == "tehran"

    def test_accepts_kebab_case(self) -> None:
        assert ShippingZoneCode("central-provinces").value == "central-provinces"

    @pytest.mark.parametrize("bad", ["", "  ", "has space", "under_score", "a" * 33, "bad!"])
    def test_rejects_malformed_codes(self, bad: str) -> None:
        with pytest.raises(InvalidShippingZoneCodeError):
            ShippingZoneCode(bad)

    def test_equality_is_by_value(self) -> None:
        assert ShippingZoneCode("TEHRAN") == ShippingZoneCode("tehran")

    def test_str_is_the_value(self) -> None:
        assert str(ShippingZoneCode("tehran")) == "tehran"


class TestDestination:
    def test_normalizes_province_and_city(self) -> None:
        destination = Destination(province="  Tehran  ", city="  Karaj ")
        assert destination.province == "Tehran"
        assert destination.city == "Karaj"

    def test_city_defaults_to_empty(self) -> None:
        assert Destination(province="Tehran").city == ""

    def test_preserves_persian_province(self) -> None:
        assert Destination(province="تهران").province == "تهران"

    @pytest.mark.parametrize("bad", ["", "   ", "x" * 101])
    def test_rejects_a_blank_or_overlong_province(self, bad: str) -> None:
        with pytest.raises(InvalidDestinationError):
            Destination(province=bad)

    def test_rejects_an_overlong_city(self) -> None:
        with pytest.raises(InvalidDestinationError):
            Destination(province="Tehran", city="c" * 101)

    def test_match_key_folds_case_and_whitespace(self) -> None:
        assert Destination(province=" Tehran ").match_key == "tehran"


class TestZonedRate:
    def _money(self, amount: str) -> Money:
        return Money(Decimal(amount), "IRR")

    def test_returns_the_zone_override_when_present(self) -> None:
        rate = ZonedRate(default=self._money("50000"), by_zone={"tehran": self._money("30000")})
        assert rate.for_zone("tehran").amount == Decimal("30000")

    def test_falls_back_to_the_default_for_an_unmatched_zone(self) -> None:
        rate = ZonedRate(default=self._money("50000"), by_zone={"tehran": self._money("30000")})
        assert rate.for_zone("isfahan").amount == Decimal("50000")

    def test_falls_back_to_the_default_when_no_zone(self) -> None:
        rate = ZonedRate(default=self._money("50000"), by_zone={"tehran": self._money("30000")})
        assert rate.for_zone(None).amount == Decimal("50000")

    def test_a_rate_with_no_overrides_is_always_the_default(self) -> None:
        rate = ZonedRate(default=self._money("50000"), by_zone={})
        assert rate.for_zone("tehran").amount == Decimal("50000")

    def test_rejects_an_override_in_a_different_currency(self) -> None:
        # Every rate in a table settles in the same currency; a mixed table is a config bug.
        with pytest.raises(InvalidZonedRateError):
            ZonedRate(default=self._money("50000"), by_zone={"tehran": Money(Decimal("10"), "USD")})
