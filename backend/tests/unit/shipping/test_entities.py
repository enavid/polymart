"""Unit tests for the ShippingMethod entity (pure Python, no framework)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.shipping.entities import ShippingMethod
from src.domain.shipping.exceptions import InvalidShippingMethodError
from src.domain.shipping.value_objects import Money, ShippingMethodCode


def _method(**overrides: object) -> ShippingMethod:
    kwargs: dict[str, object] = {
        "code": ShippingMethodCode("standard"),
        "name": "Standard post",
        "price": Money(Decimal("50000"), "IRR"),
        "min_days": 3,
        "max_days": 5,
    }
    kwargs.update(overrides)
    return ShippingMethod(**kwargs)  # type: ignore[arg-type]


class TestShippingMethod:
    def test_builds_a_valid_method(self) -> None:
        method = _method()
        assert method.code.value == "standard"
        assert method.name == "Standard post"
        assert method.price.amount == Decimal("50000")
        assert (method.min_days, method.max_days) == (3, 5)

    def test_trims_the_name(self) -> None:
        assert _method(name="  Express  ").name == "Express"

    def test_a_same_day_window_is_valid(self) -> None:
        method = _method(min_days=0, max_days=0)
        assert (method.min_days, method.max_days) == (0, 0)

    def test_rejects_a_blank_name(self) -> None:
        with pytest.raises(InvalidShippingMethodError):
            _method(name="   ")

    def test_rejects_a_window_that_ends_before_it_starts(self) -> None:
        with pytest.raises(InvalidShippingMethodError):
            _method(min_days=5, max_days=3)

    def test_rejects_a_negative_day(self) -> None:
        with pytest.raises(InvalidShippingMethodError):
            _method(min_days=-1)

    def test_rejects_a_boolean_day_count(self) -> None:
        with pytest.raises(InvalidShippingMethodError):
            _method(min_days=True)


from src.domain.shipping.entities import ShippingZone  # noqa: E402
from src.domain.shipping.exceptions import InvalidShippingZoneError  # noqa: E402
from src.domain.shipping.value_objects import Destination, ShippingZoneCode  # noqa: E402


def _zone(**overrides: object) -> ShippingZone:
    kwargs: dict[str, object] = {
        "code": ShippingZoneCode("tehran"),
        "name": "Tehran",
        "provinces": frozenset({"تهران"}),
    }
    kwargs.update(overrides)
    return ShippingZone(**kwargs)  # type: ignore[arg-type]


class TestShippingZone:
    def test_builds_a_valid_zone(self) -> None:
        zone = _zone()
        assert zone.code.value == "tehran"
        assert zone.name == "Tehran"

    def test_covers_a_configured_province(self) -> None:
        assert _zone().covers(Destination(province="تهران")) is True

    def test_covers_is_case_and_whitespace_insensitive(self) -> None:
        zone = _zone(provinces=frozenset({"Tehran"}))
        assert zone.covers(Destination(province="  tehran ")) is True

    def test_does_not_cover_an_unlisted_province(self) -> None:
        assert _zone().covers(Destination(province="اصفهان")) is False

    def test_a_city_scoped_zone_covers_only_the_listed_cities(self) -> None:
        # cities narrows the zone: the province must match AND the city be listed.
        zone = _zone(cities=frozenset({"تهران"}))
        assert zone.covers(Destination(province="تهران", city="تهران")) is True
        assert zone.covers(Destination(province="تهران", city="کرج")) is False

    def test_a_province_wide_zone_covers_any_city(self) -> None:
        assert _zone().covers(Destination(province="تهران", city="anywhere")) is True

    def test_trims_the_name(self) -> None:
        assert _zone(name="  Tehran  ").name == "Tehran"

    def test_rejects_a_blank_name(self) -> None:
        with pytest.raises(InvalidShippingZoneError):
            _zone(name="   ")

    def test_rejects_an_empty_province_set(self) -> None:
        # A zone that covers nothing is a misconfiguration.
        with pytest.raises(InvalidShippingZoneError):
            _zone(provinces=frozenset())

    def test_rejects_a_blank_province_entry(self) -> None:
        with pytest.raises(InvalidShippingZoneError):
            _zone(provinces=frozenset({"تهران", "   "}))

    def test_rejects_a_blank_city_entry(self) -> None:
        with pytest.raises(InvalidShippingZoneError):
            _zone(cities=frozenset({"تهران", "   "}))
