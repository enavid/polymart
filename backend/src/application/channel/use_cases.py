"""Channel use cases (interactors).

Each use case orchestrates the domain to fulfil one application intent. They are
pure orchestration: dependencies arrive via constructor injection, business
rules live in the domain, and side effects (logging) are observable.

Channels gate currency and pricing for everything downstream, so every mutation
emits a structured, audit-friendly event.
"""
from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.application.channel.ports import ChannelRepository
from src.domain.channel.entities import Channel
from src.domain.channel.exceptions import ChannelAlreadyExistsError
from src.domain.channel.value_objects import ChannelSlug, Currency

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CreateChannelCommand:
    """Input for creating a channel. Raw strings are validated by the domain."""

    name: str
    slug: str
    currency: str
    is_active: bool = True


class CreateChannel:
    """Register a new selling channel."""

    def __init__(self, repository: ChannelRepository) -> None:
        self._repository = repository

    def execute(self, command: CreateChannelCommand) -> Channel:
        # Build value objects first: invalid input fails fast, before any I/O.
        channel = Channel(
            slug=ChannelSlug(command.slug),
            name=command.name,
            currency=Currency(command.currency),
            is_active=command.is_active,
        )
        slug = channel.slug.value

        # Pre-check for a clean error; the repository remains the source of
        # truth and will still raise on a concurrent insert.
        if self._repository.exists_by_slug(slug):
            logger.warning("channel_create_rejected_duplicate", slug=slug)
            raise ChannelAlreadyExistsError(slug)

        persisted = self._repository.add(channel)
        logger.info(
            "channel_created",
            channel_id=persisted.id,
            slug=slug,
            currency=persisted.currency.code,
            is_active=persisted.is_active,
        )
        return persisted


class SetChannelStatus:
    """Activate or deactivate an existing channel."""

    def __init__(self, repository: ChannelRepository) -> None:
        self._repository = repository

    def execute(self, *, slug: str, active: bool) -> Channel:
        channel = self._repository.get_by_slug(slug)
        changed = channel.set_active(active=active)
        if not changed:
            logger.info("channel_status_unchanged", slug=slug, is_active=active)
            return channel

        updated = self._repository.update(channel)
        logger.info(
            "channel_status_changed",
            channel_id=updated.id,
            slug=slug,
            is_active=updated.is_active,
        )
        return updated


class GetChannel:
    """Retrieve a single channel by slug."""

    def __init__(self, repository: ChannelRepository) -> None:
        self._repository = repository

    def execute(self, *, slug: str) -> Channel:
        channel = self._repository.get_by_slug(slug)
        logger.debug("channel_retrieved", slug=slug)
        return channel


class ListChannels:
    """List channels, optionally restricted to active ones."""

    def __init__(self, repository: ChannelRepository) -> None:
        self._repository = repository

    def execute(self, *, only_active: bool = False) -> list[Channel]:
        channels = self._repository.list_all()
        if only_active:
            channels = [c for c in channels if c.is_active]
        logger.debug("channels_listed", count=len(channels), only_active=only_active)
        return channels
