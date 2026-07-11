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


class ShippingMethodNotFoundError(ShippingError):
    """Raised when a requested method is not offered in the channel."""

    def __init__(self, channel: str, code: str) -> None:
        super().__init__(f"shipping method {code!r} is not available in channel {channel!r}")
        self.channel = channel
        self.code = code
