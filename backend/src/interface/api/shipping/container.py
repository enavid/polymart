"""Composition root for the shipping slice.

The only place that wires the concrete settings-backed reader into the shipping use case.
Views depend on these factories, never on the infrastructure layer directly.
"""

from __future__ import annotations

from src.application.shipping.use_cases import ListShippingMethods
from src.infrastructure.shipping.methods import SettingsShippingMethodReader


def build_list_shipping_methods() -> ListShippingMethods:
    return ListShippingMethods(SettingsShippingMethodReader())
