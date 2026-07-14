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
    """Read boundary onto the configured tax rate of a channel, per tax class."""

    @abstractmethod
    def rate_for(self, channel: str, tax_class: str = "standard") -> TaxRate | None:
        """Return the channel's rate for a tax class, or ``None`` if that class is not taxed.

        The ``standard`` class falls back to the channel's headline rate; any other class that
        the channel does not map to a rate (an exempt class) levies no tax (``None``).
        """
