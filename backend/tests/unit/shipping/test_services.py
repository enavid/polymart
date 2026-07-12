"""Unit tests for the shipping domain services (pure Python, no framework)."""

from __future__ import annotations

from src.domain.shipping.entities import ShippingZone
from src.domain.shipping.services import resolve_zone
from src.domain.shipping.value_objects import Destination, ShippingZoneCode

_TEHRAN = ShippingZone(
    code=ShippingZoneCode("tehran"), name="Tehran", provinces=frozenset({"تهران"})
)
_NORTH = ShippingZone(
    code=ShippingZoneCode("north"), name="North", provinces=frozenset({"گیلان", "مازندران"})
)


def _to(province: str, city: str = "") -> Destination:
    return Destination(province=province, city=city)


class TestResolveZone:
    def test_returns_the_zone_that_covers_the_province(self) -> None:
        assert resolve_zone(_to("مازندران"), (_TEHRAN, _NORTH)) is _NORTH

    def test_returns_none_when_no_zone_covers_the_province(self) -> None:
        assert resolve_zone(_to("اصفهان"), (_TEHRAN, _NORTH)) is None

    def test_returns_none_when_there_are_no_zones(self) -> None:
        assert resolve_zone(_to("تهران"), ()) is None

    def test_matches_case_and_whitespace_insensitively(self) -> None:
        latin = ShippingZone(
            code=ShippingZoneCode("tehran"), name="Tehran", provinces=frozenset({"Tehran"})
        )
        assert resolve_zone(_to(" tehran "), (latin,)) is latin

    def test_returns_the_first_matching_zone_when_two_overlap(self) -> None:
        # Zones should be disjoint; if they overlap, the first configured wins (deterministic).
        other = ShippingZone(
            code=ShippingZoneCode("other"), name="Other", provinces=frozenset({"تهران"})
        )
        assert resolve_zone(_to("تهران"), (_TEHRAN, other)) is _TEHRAN

    def test_a_city_scoped_zone_ordered_first_wins_for_its_city(self) -> None:
        # A fine city zone before a broad province zone lets specific rates layer over general.
        city_zone = ShippingZone(
            code=ShippingZoneCode("tehran-city"),
            name="Tehran City",
            provinces=frozenset({"تهران"}),
            cities=frozenset({"تهران"}),
        )
        province_zone = ShippingZone(
            code=ShippingZoneCode("tehran"), name="Tehran", provinces=frozenset({"تهران"})
        )
        zones = (city_zone, province_zone)
        assert resolve_zone(_to("تهران", "تهران"), zones) is city_zone
        # A different city in the province falls through to the province-wide zone.
        assert resolve_zone(_to("تهران", "کرج"), zones) is province_zone
