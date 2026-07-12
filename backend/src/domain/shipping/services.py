"""Domain services for the shipping context (pure Python, no framework).

A domain service holds a rule that does not belong to a single entity or value object.
``resolve_zone`` picks the shipping zone a destination's province falls into -- the one
geographic decision that governs which rate applies -- so it is defined and unit-tested in
the domain rather than in an adapter.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.shipping.entities import ShippingZone
from src.domain.shipping.value_objects import Destination


def resolve_zone(destination: Destination, zones: Sequence[ShippingZone]) -> ShippingZone | None:
    """Return the first zone that covers ``destination``, or ``None`` if none does.

    Matching considers the destination's province and (for a city-scoped zone) its city. Order
    matters: a fine city zone listed before a broad province zone wins, so the caller can layer
    specific rates over general ones. Overlapping zones resolve to the first configured one, so
    the result is deterministic regardless of the input data.
    """
    for zone in zones:
        if zone.covers(destination):
            return zone
    return None
