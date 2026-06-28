"""Unit tests for the access use cases (no Django, no database).

The use cases orchestrate role assignment and per-channel grants through the
``AccessControlGateway`` port. Exercised here against an in-memory fake gateway,
a fake channel repository, and a fake audit recorder, so the durable audit trail
and slug->id resolution are verified without guardian or the ORM.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.access.ports import AccessControlGateway
from src.application.access.use_cases import AssignRole, GrantChannelManagement
from src.application.audit.ports import AuditRecorder
from src.application.channel.ports import ChannelRepository
from src.domain.audit.entities import FieldChange
from src.domain.channel.entities import Channel
from src.domain.channel.exceptions import ChannelNotFoundError
from src.domain.channel.value_objects import ChannelSlug, Currency


class RecordedAudit:
    """One captured audit call (the keyword facts the use case supplied)."""

    def __init__(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None,
        changes: tuple[FieldChange, ...],
    ) -> None:
        self.action = action
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.actor = actor
        self.changes = changes


class FakeAuditRecorder(AuditRecorder):
    """Captures audit calls in memory so the use case's trail is assertable."""

    def __init__(self) -> None:
        self.calls: list[RecordedAudit] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: Sequence[FieldChange] = (),
    ) -> None:
        self.calls.append(RecordedAudit(action, resource_type, resource_id, actor, tuple(changes)))


class FakeAccessControlGateway(AccessControlGateway):
    """Records what was assigned/granted so the use cases can be asserted on."""

    def __init__(self) -> None:
        self.roles: list[tuple[int, str]] = []
        self.channel_grants: list[tuple[int, int]] = []
        self.manageable: set[tuple[int, int]] = set()

    def assign_role(self, user_id: int, role_name: str) -> None:
        self.roles.append((user_id, role_name))

    def grant_channel_management(self, user_id: int, channel_id: int) -> None:
        self.channel_grants.append((user_id, channel_id))
        self.manageable.add((user_id, channel_id))

    def can_manage_channel(self, user_id: int, channel_id: int) -> bool:
        return (user_id, channel_id) in self.manageable


class FakeChannelRepository(ChannelRepository):
    """Minimal channel lookup for resolving a slug to its identity."""

    def __init__(self) -> None:
        self._by_slug: dict[str, Channel] = {}
        self._sequence = 0

    def add(self, channel: Channel) -> Channel:
        self._sequence += 1
        channel.id = self._sequence
        self._by_slug[channel.slug.value] = channel
        return channel

    def get_by_slug(self, slug: str) -> Channel:
        try:
            return self._by_slug[slug]
        except KeyError:
            raise ChannelNotFoundError(slug) from None

    def exists_by_slug(self, slug: str) -> bool:
        return slug in self._by_slug

    def list_all(self) -> list[Channel]:
        return list(self._by_slug.values())

    def update(self, channel: Channel) -> Channel:
        self._by_slug[channel.slug.value] = channel
        return channel


@pytest.fixture
def gateway() -> FakeAccessControlGateway:
    return FakeAccessControlGateway()


@pytest.fixture
def audit() -> FakeAuditRecorder:
    return FakeAuditRecorder()


@pytest.fixture
def channels() -> FakeChannelRepository:
    repo = FakeChannelRepository()
    repo.add(Channel(slug=ChannelSlug("coffee"), name="Coffee", currency=Currency("IRR")))
    return repo


class TestAssignRole:
    def test_assigns_the_role_through_the_gateway(
        self, gateway: FakeAccessControlGateway, audit: FakeAuditRecorder
    ) -> None:
        AssignRole(gateway, audit).execute(user_id=7, role_name="channel_admin")

        assert gateway.roles == [(7, "channel_admin")]

    def test_records_the_acting_user_in_the_audit_event(
        self, gateway: FakeAccessControlGateway, audit: FakeAuditRecorder
    ) -> None:
        with capture_logs() as logs:
            AssignRole(gateway, audit).execute(user_id=7, role_name="channel_admin", actor="root")

        events = [e for e in logs if e["event"] == "role_assigned"]
        assert events and events[0]["actor"] == "root"
        assert events[0]["role"] == "channel_admin"
        assert events[0]["user_id"] == 7

    def test_writes_a_durable_audit_entry(
        self, gateway: FakeAccessControlGateway, audit: FakeAuditRecorder
    ) -> None:
        # Granting a role is a privileged change; it must leave a durable trail
        # naming the subject user, the role, and who acted -- not just a log line.
        AssignRole(gateway, audit).execute(user_id=7, role_name="channel_admin", actor="root")

        assert len(audit.calls) == 1
        call = audit.calls[0]
        assert call.action == "access.role_assigned"
        assert call.resource_type == "user"
        assert call.resource_id == "7"
        assert call.actor == "root"
        assert call.changes == (FieldChange(field="role", after="channel_admin"),)


class TestGrantChannelManagement:
    def test_grants_object_scope_for_the_resolved_channel(
        self,
        gateway: FakeAccessControlGateway,
        channels: FakeChannelRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        GrantChannelManagement(gateway, channels, audit).execute(user_id=7, channel_slug="coffee")

        coffee_id = channels.get_by_slug("coffee").id
        assert coffee_id is not None
        assert gateway.channel_grants == [(7, coffee_id)]
        assert gateway.can_manage_channel(7, coffee_id)

    def test_raises_when_the_channel_does_not_exist(
        self,
        gateway: FakeAccessControlGateway,
        channels: FakeChannelRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        with pytest.raises(ChannelNotFoundError):
            GrantChannelManagement(gateway, channels, audit).execute(
                user_id=7, channel_slug="ghost"
            )

        assert gateway.channel_grants == []
        # A rejected grant leaves nothing on the trail.
        assert audit.calls == []

    def test_records_the_acting_user_in_the_audit_event(
        self,
        gateway: FakeAccessControlGateway,
        channels: FakeChannelRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        with capture_logs() as logs:
            GrantChannelManagement(gateway, channels, audit).execute(
                user_id=7, channel_slug="coffee", actor="root"
            )

        events = [e for e in logs if e["event"] == "channel_management_granted"]
        assert events and events[0]["actor"] == "root"
        assert events[0]["channel_slug"] == "coffee"
        assert events[0]["user_id"] == 7

    def test_writes_a_durable_audit_entry(
        self,
        gateway: FakeAccessControlGateway,
        channels: FakeChannelRepository,
        audit: FakeAuditRecorder,
    ) -> None:
        GrantChannelManagement(gateway, channels, audit).execute(
            user_id=7, channel_slug="coffee", actor="root"
        )

        assert len(audit.calls) == 1
        call = audit.calls[0]
        assert call.action == "access.channel_management_granted"
        assert call.resource_type == "user"
        assert call.resource_id == "7"
        assert call.actor == "root"
        assert call.changes == (FieldChange(field="managed_channel", after="coffee"),)
