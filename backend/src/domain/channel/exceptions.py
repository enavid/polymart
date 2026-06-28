"""Domain exceptions for the channel context.

These are pure-Python exceptions with no framework coupling. The interface layer
is responsible for translating them into transport-level responses (HTTP codes).
"""

from __future__ import annotations


class ChannelError(Exception):
    """Base class for every channel domain error."""


class InvalidCurrencyCodeError(ChannelError):
    """Raised when a currency code does not match the ISO 4217 alpha format."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid currency code: {value!r}")
        self.value = value


class InvalidChannelSlugError(ChannelError):
    """Raised when a slug is empty, too long, or not URL-safe kebab-case."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid channel slug: {value!r}")
        self.value = value


class InvalidChannelNameError(ChannelError):
    """Raised when a channel display name is blank or exceeds the length limit."""

    def __init__(self, value: str) -> None:
        super().__init__(f"invalid channel name: {value!r}")
        self.value = value


class ChannelNotFoundError(ChannelError):
    """Raised when a channel cannot be located by its slug."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"channel not found: {slug!r}")
        self.slug = slug


class ChannelAlreadyExistsError(ChannelError):
    """Raised when creating a channel whose slug is already taken."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"channel already exists: {slug!r}")
        self.slug = slug
