"""Ports (interfaces) for the channel use cases.

The application layer depends only on these abstractions. Concrete adapters
(Django ORM, in-memory fakes) live elsewhere and are injected at the composition
root, keeping the dependency rule pointing inward.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.channel.entities import Channel


class ChannelRepository(ABC):
    """Persistence boundary for the Channel aggregate.

    Implementations MUST translate storage-specific failures into domain
    exceptions (``ChannelNotFoundError``, ``ChannelAlreadyExistsError``) so that callers
    never see infrastructure leaks.
    """

    @abstractmethod
    def add(self, channel: Channel) -> Channel:
        """Persist a new channel and return it with its assigned identity.

        Raises ``ChannelAlreadyExistsError`` if the slug is already taken.
        """

    @abstractmethod
    def get_by_slug(self, slug: str) -> Channel:
        """Return the channel with this slug or raise ``ChannelNotFoundError``."""

    @abstractmethod
    def exists_by_slug(self, slug: str) -> bool:
        """Return whether a channel with this slug already exists."""

    @abstractmethod
    def list_all(self) -> list[Channel]:
        """Return every channel, ordered by slug for deterministic output."""

    @abstractmethod
    def update(self, channel: Channel) -> Channel:
        """Persist changes to an existing channel.

        Raises ``ChannelNotFoundError`` if the channel is not present.
        """
