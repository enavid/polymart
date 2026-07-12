"""Domain exceptions for the shipping context.

A single base (``ShippingError``) lets a caller catch the whole family; the specific
subclasses carry the meaning a use case or transport needs. Pure Python -- no framework.
"""

from __future__ import annotations


class ShippingError(Exception):
    """Base class for every shipping-domain error."""


class InvalidMoneyError(ShippingError):
    """Raised when a shipping price is not a valid, representable, non-negative value."""


class InvalidShippingMethodCodeError(ShippingError):
    """Raised when a shipping-method code is structurally malformed."""


class InvalidShippingMethodError(ShippingError):
    """Raised when a shipping method's name or delivery window is invalid."""


class InvalidShippingZoneCodeError(ShippingError):
    """Raised when a shipping-zone code is structurally malformed."""


class InvalidDestinationError(ShippingError):
    """Raised when a destination's province is blank or too long."""


class InvalidZonedRateError(ShippingError):
    """Raised when a rate table mixes currencies (a per-zone override must match the default)."""


class InvalidWeightTableError(ShippingError):
    """Raised for a weight table that is empty, mis-ordered, mixed-currency, or has no overflow."""


class InvalidShippingZoneError(ShippingError):
    """Raised when a shipping zone's name or province set is invalid."""


class ShippingMethodNotFoundError(ShippingError):
    """Raised when a requested method is not offered in the channel."""

    def __init__(self, channel: str, code: str) -> None:
        super().__init__(f"shipping method {code!r} is not available in channel {channel!r}")
        self.channel = channel
        self.code = code
