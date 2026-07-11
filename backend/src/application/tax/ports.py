"""Ports (interfaces) for the tax use cases.

The application layer depends only on this abstraction; the concrete adapter (a
settings-backed reader, an in-memory fake) is injected at the composition root, keeping the
dependency rule pointing inward. In this slice the reader is the whole infrastructure
boundary: it answers "what tax rate does this channel levy?" -- the source (config today, an
admin-managed table tomorrow) is invisible here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.tax.value_objects import TaxRate


class TaxRateReader(ABC):
    """Read boundary onto the configured tax rate of a channel."""

    @abstractmethod
    def rate_for(self, channel: str) -> TaxRate | None:
        """Return the channel's tax rate, or ``None`` if the channel levies no tax."""
