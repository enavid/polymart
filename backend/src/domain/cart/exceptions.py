"""Domain exceptions for the cart context.

Pure-Python exceptions with no framework coupling. The interface layer translates
them into transport-level responses (HTTP codes).
"""

from __future__ import annotations


class CartError(Exception):
    """Base class for every cart domain error."""


class InvalidSkuError(CartError):
    """Raised when a cart line references a SKU that is empty, too long, or malformed."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid sku: {value!r}")
        self.value = value


class InvalidCartQuantityError(CartError):
    """Raised when a line quantity is not a positive integer within range."""

    def __init__(self, value: object) -> None:
        super().__init__(f"invalid cart quantity: {value!r}")
        self.value = value


class InvalidMoneyError(CartError):
    """Raised when a monetary amount is not a non-negative, finite, bounded Decimal."""

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid money: {detail}")
        self.detail = detail


class InvalidChannelReferenceError(CartError):
    """Raised when a channel reference is blank or exceeds the length limit."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid channel reference: {value!r}")
        self.value = value


class CurrencyMismatchError(CartError):
    """Raised when a line's price currency differs from the cart's channel currency.

    A cart is priced in a single currency (its channel's). A line priced in another
    currency would make the total meaningless, so it is refused rather than summed.
    """

    def __init__(self, expected: str, found: str) -> None:
        super().__init__(f"currency mismatch: expected {expected!r}, found {found!r}")
        self.expected = expected
        self.found = found


class CartLineNotFoundError(CartError):
    """Raised when updating or removing a line that the cart does not contain."""

    def __init__(self, sku: str) -> None:
        super().__init__(f"cart has no line for sku: {sku!r}")
        self.sku = sku


class DuplicateCartLineError(CartError):
    """Raised when a cart is built with the same SKU on more than one line."""

    def __init__(self, sku: str) -> None:
        super().__init__(f"duplicate cart line for sku: {sku!r}")
        self.sku = sku


class UnknownChannelError(CartError):
    """Raised when a cart operation references a channel that does not exist."""

    def __init__(self, channel: str) -> None:
        super().__init__(f"unknown channel: {channel!r}")
        self.channel = channel


class VariantNotFoundError(CartError):
    """Raised when adding a SKU that no catalog variant matches."""

    def __init__(self, sku: str) -> None:
        super().__init__(f"unknown variant: {sku!r}")
        self.sku = sku


class VariantNotPurchasableError(CartError):
    """Raised when adding a variant that has no price in the cart's channel.

    Without a per-channel price the line cannot be sold in that channel, so it is
    refused at add time rather than persisted as an unpriceable line.
    """

    def __init__(self, sku: str, channel: str) -> None:
        super().__init__(f"variant {sku!r} is not purchasable in channel {channel!r}")
        self.sku = sku
        self.channel = channel
