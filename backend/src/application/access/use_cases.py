"""Access (RBAC) use cases: assigning roles and per-channel scope.

Pure orchestration over the ``AccessControlGateway`` port. Granting access is a
security-sensitive mutation, so every assignment emits a structured, audit-ready
event recording who acted, on whom, and over what.
"""

from __future__ import annotations

import structlog

from src.application.access.ports import AccessControlGateway
from src.application.channel.ports import ChannelRepository
from src.domain.channel.exceptions import ChannelNotFoundError

logger = structlog.get_logger(__name__)


class AssignRole:
    """Assign a global role (Django Group) to a user."""

    def __init__(self, gateway: AccessControlGateway) -> None:
        self._gateway = gateway

    def execute(self, *, user_id: int, role_name: str, actor: str | None = None) -> None:
        self._gateway.assign_role(user_id, role_name)
        logger.info("role_assigned", user_id=user_id, role=role_name, actor=actor)


class GrantChannelManagement:
    """Grant a user object-scoped management of a single channel."""

    def __init__(
        self, gateway: AccessControlGateway, channel_repository: ChannelRepository
    ) -> None:
        self._gateway = gateway
        self._channels = channel_repository

    def execute(self, *, user_id: int, channel_slug: str, actor: str | None = None) -> None:
        # Resolve the slug to the channel's identity first; a missing channel
        # raises ChannelNotFoundError before any grant is recorded.
        channel = self._channels.get_by_slug(channel_slug)
        channel_id = channel.id
        if channel_id is None:  # pragma: no cover - persisted channels always carry an id
            raise ChannelNotFoundError(channel_slug)
        self._gateway.grant_channel_management(user_id, channel_id)
        logger.info(
            "channel_management_granted",
            user_id=user_id,
            channel_id=channel_id,
            channel_slug=channel_slug,
            actor=actor,
        )
