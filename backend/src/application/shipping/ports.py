"""Ports (interfaces) for the shipping use cases.

The application layer depends only on this abstraction; the concrete adapter (a
settings-backed reader, an in-memory fake) is injected at the composition root, keeping
the dependency rule pointing inward. In this flat-rate slice the reader is the whole
infrastructure boundary: it answers "which methods does this channel offer?" and "what is
this one method?" -- the source (config today, a table tomorrow) is invisible here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.shipping.entities import ShippingMethod
from src.domain.shipping.value_objects import Destination


class ShippingMethodReader(ABC):
    """Read boundary onto the configured shipping methods of a channel.

    A ``destination`` (optional) selects the rate: a method's price is resolved for the
    zone the destination's province falls into, falling back to the method's default rate
    when the destination is absent or falls in no configured zone.
    """

    @abstractmethod
    def available_for(
        self, channel: str, destination: Destination | None = None
    ) -> tuple[ShippingMethod, ...]:
        """Return the channel's offered methods (empty tuple if none configured).

        Each method's price is resolved for ``destination``'s zone (or the default rate).
        """

    @abstractmethod
    def get(
        self, channel: str, code: str, destination: Destination | None = None
    ) -> ShippingMethod | None:
        """Return the channel's method by code (priced for ``destination``), or ``None``."""
