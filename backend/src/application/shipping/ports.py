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


class ShippingMethodReader(ABC):
    """Read boundary onto the configured shipping methods of a channel."""

    @abstractmethod
    def available_for(self, channel: str) -> tuple[ShippingMethod, ...]:
        """Return the channel's offered methods (empty tuple if none configured)."""

    @abstractmethod
    def get(self, channel: str, code: str) -> ShippingMethod | None:
        """Return the channel's method by code, or ``None`` if it is not offered."""
