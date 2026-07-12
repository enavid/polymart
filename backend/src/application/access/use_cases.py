"""Access (RBAC) use cases: assigning roles and per-channel scope.

Pure orchestration over the ``AccessControlGateway`` port. Granting access is a
security-sensitive mutation, so every assignment both emits a structured log and
writes a durable audit entry recording who acted, on whom, and over what.
"""

from __future__ import annotations

import structlog

from src.application.access.ports import AccessControlGateway
from src.application.audit.ports import AuditRecorder
from src.application.channel.ports import ChannelRepository
from src.application.inventory.ports import StockSourceRepository
from src.domain.audit.entities import FieldChange
from src.domain.channel.exceptions import ChannelNotFoundError
from src.domain.inventory.exceptions import StockSourceNotFoundError
from src.domain.inventory.value_objects import StockSourceCode

logger = structlog.get_logger(__name__)

# The audited resource is the subject user whose access changed; the action names
# stay in the "access." namespace so the trail is greppable by area.
_RESOURCE_USER = "user"
_ACTION_ROLE_ASSIGNED = "access.role_assigned"
_ACTION_CHANNEL_MANAGEMENT_GRANTED = "access.channel_management_granted"
_ACTION_STOCK_SOURCE_MANAGEMENT_GRANTED = "access.stock_source_management_granted"


class AssignRole:
    """Assign a global role (Django Group) to a user."""

    def __init__(self, gateway: AccessControlGateway, audit: AuditRecorder) -> None:
        self._gateway = gateway
        self._audit = audit

    def execute(self, *, user_id: int, role_name: str, actor: str | None = None) -> None:
        self._gateway.assign_role(user_id, role_name)
        logger.info("role_assigned", user_id=user_id, role=role_name, actor=actor)
        self._audit.record(
            action=_ACTION_ROLE_ASSIGNED,
            resource_type=_RESOURCE_USER,
            resource_id=str(user_id),
            actor=actor,
            changes=(FieldChange(field="role", after=role_name),),
        )


class GrantChannelManagement:
    """Grant a user object-scoped management of a single channel."""

    def __init__(
        self,
        gateway: AccessControlGateway,
        channel_repository: ChannelRepository,
        audit: AuditRecorder,
    ) -> None:
        self._gateway = gateway
        self._channels = channel_repository
        self._audit = audit

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
        self._audit.record(
            action=_ACTION_CHANNEL_MANAGEMENT_GRANTED,
            resource_type=_RESOURCE_USER,
            resource_id=str(user_id),
            actor=actor,
            changes=(FieldChange(field="managed_channel", after=channel_slug),),
        )


class GrantStockSourceManagement:
    """Grant a user object-scoped management of a single stock source (warehouse)."""

    def __init__(
        self,
        gateway: AccessControlGateway,
        sources: StockSourceRepository,
        audit: AuditRecorder,
    ) -> None:
        self._gateway = gateway
        self._sources = sources
        self._audit = audit

    def execute(self, *, user_id: int, source_code: str, actor: str | None = None) -> None:
        # Resolve the code to the source's identity first; a missing source raises
        # StockSourceNotFoundError before any grant is recorded.
        source = self._sources.get(StockSourceCode(source_code))
        source_id = source.id
        if source_id is None:  # pragma: no cover - persisted sources always carry an id
            raise StockSourceNotFoundError(source_code)
        self._gateway.grant_stock_source_management(user_id, source_id)
        logger.info(
            "stock_source_management_granted",
            user_id=user_id,
            source_id=source_id,
            source_code=source_code,
            actor=actor,
        )
        self._audit.record(
            action=_ACTION_STOCK_SOURCE_MANAGEMENT_GRANTED,
            resource_type=_RESOURCE_USER,
            resource_id=str(user_id),
            actor=actor,
            changes=(FieldChange(field="managed_stock_source", after=source_code),),
        )
