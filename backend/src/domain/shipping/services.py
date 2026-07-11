"""Domain services for the shipping context (pure Python, no framework).

A domain service holds a rule that does not belong to a single entity or value object.
``resolve_zone`` picks the shipping zone a destination's province falls into -- the one
geographic decision that governs which rate applies -- so it is defined and unit-tested in
the domain rather than in an adapter.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.shipping.entities import ShippingZone


def resolve_zone(province: str, zones: Sequence[ShippingZone]) -> ShippingZone | None:
    """Return the first zone that covers ``province``, or ``None`` if none does.

    Zones are expected to be disjoint; if two overlap, the first configured one wins, so the
    result is deterministic regardless of the input data.
    """
    for zone in zones:
        if zone.covers(province):
            return zone
    return None
