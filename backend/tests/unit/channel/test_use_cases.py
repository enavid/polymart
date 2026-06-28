"""Unit tests for the channel use cases.

The use cases are exercised against an in-memory fake repository and a fake audit
recorder: no Django, no database. This is the payoff of the dependency rule --
business orchestration is testable in isolation and at speed.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.channel.ports import ChannelRepository
from src.application.channel.use_cases import (
    CreateChannel,
    CreateChannelCommand,
    GetChannel,
    ListChannels,
    SetChannelStatus,
)
from src.domain.audit.entities import FieldChange
from src.domain.channel.entities import Channel
from src.domain.channel.exceptions import (
    ChannelAlreadyExistsError,
    ChannelNotFoundError,
    InvalidCurrencyCodeError,
)


class FakeChannelRepository(ChannelRepository):
    """In-memory stand-in keyed by slug, mimicking the real repo's contract."""

    def __init__(self) -> None:
        self._by_slug: dict[str, Channel] = {}
        self._sequence = 0

    def add(self, channel: Channel) -> Channel:
        slug = channel.slug.value
        if slug in self._by_slug:
            raise ChannelAlreadyExistsError(slug)
        self._sequence += 1
        channel.id = self._sequence
        self._by_slug[slug] = channel
        return channel

    def get_by_slug(self, slug: str) -> Channel:
        try:
            return self._by_slug[slug]
        except KeyError:
            raise ChannelNotFoundError(slug) from None

    def exists_by_slug(self, slug: str) -> bool:
        return slug in self._by_slug

    def list_all(self) -> list[Channel]:
        return [self._by_slug[s] for s in sorted(self._by_slug)]

    def update(self, channel: Channel) -> Channel:
        slug = channel.slug.value
        if slug not in self._by_slug:
            raise ChannelNotFoundError(slug)
        self._by_slug[slug] = channel
        return channel


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


@pytest.fixture
def repo() -> FakeChannelRepository:
    return FakeChannelRepository()


@pytest.fixture
def audit() -> FakeAuditRecorder:
    return FakeAuditRecorder()


class TestCreateChannel:
    def test_persists_and_returns_a_channel_with_an_identity(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        use_case = CreateChannel(repo, audit)

        channel = use_case.execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        assert channel.id is not None
        assert channel.slug.value == "coffee"
        assert channel.currency.code == "IRR"
        assert channel.is_active is True
        assert repo.exists_by_slug("coffee")

    def test_rejects_a_duplicate_slug(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        use_case = CreateChannel(repo, audit)
        use_case.execute(CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR"))

        with pytest.raises(ChannelAlreadyExistsError):
            use_case.execute(CreateChannelCommand(name="Other", slug="coffee", currency="USD"))

    def test_does_not_persist_when_the_currency_is_invalid(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        use_case = CreateChannel(repo, audit)

        with pytest.raises(InvalidCurrencyCodeError):
            use_case.execute(CreateChannelCommand(name="Coffee", slug="coffee", currency="toman"))

        assert repo.list_all() == []

    def test_can_create_an_initially_inactive_channel(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        use_case = CreateChannel(repo, audit)

        channel = use_case.execute(
            CreateChannelCommand(name="Draft", slug="draft", currency="IRR", is_active=False)
        )

        assert channel.is_active is False

    def test_records_the_acting_user_in_the_audit_event(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        # Channel mutations gate currency/pricing; the audit trail must say who
        # made the change, not just that it happened.
        with capture_logs() as logs:
            CreateChannel(repo, audit).execute(
                CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR"),
                actor="operator",
            )

        events = [entry for entry in logs if entry["event"] == "channel_created"]
        assert events and events[0]["actor"] == "operator"

    def test_writes_a_durable_audit_entry(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        channel = CreateChannel(repo, audit).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR"),
            actor="operator",
        )

        assert len(audit.calls) == 1
        call = audit.calls[0]
        assert call.action == "channel.created"
        assert call.resource_type == "channel"
        assert call.resource_id == str(channel.id)
        assert call.actor == "operator"
        # Creation captures "after" values only.
        recorded = {change.field: (change.before, change.after) for change in call.changes}
        assert recorded == {
            "slug": (None, "coffee"),
            "currency": (None, "IRR"),
            "is_active": (None, True),
        }

    def test_does_not_audit_a_rejected_duplicate(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        use_case = CreateChannel(repo, audit)
        use_case.execute(CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR"))

        with pytest.raises(ChannelAlreadyExistsError):
            use_case.execute(CreateChannelCommand(name="Other", slug="coffee", currency="USD"))

        # Only the first, successful creation is on the trail.
        assert len(audit.calls) == 1


class TestSetChannelStatus:
    def test_deactivates_an_existing_channel(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        CreateChannel(repo, audit).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        channel = SetChannelStatus(repo, audit).execute(slug="coffee", active=False)

        assert channel.is_active is False
        assert repo.get_by_slug("coffee").is_active is False

    def test_is_idempotent(self, repo: FakeChannelRepository, audit: FakeAuditRecorder) -> None:
        CreateChannel(repo, audit).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        SetChannelStatus(repo, audit).execute(slug="coffee", active=True)
        channel = SetChannelStatus(repo, audit).execute(slug="coffee", active=True)

        assert channel.is_active is True

    def test_raises_when_the_channel_is_unknown(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        with pytest.raises(ChannelNotFoundError):
            SetChannelStatus(repo, audit).execute(slug="ghost", active=False)

    def test_records_the_acting_user_in_the_audit_event(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        CreateChannel(repo, audit).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        with capture_logs() as logs:
            SetChannelStatus(repo, audit).execute(slug="coffee", active=False, actor="operator")

        events = [entry for entry in logs if entry["event"] == "channel_status_changed"]
        assert events and events[0]["actor"] == "operator"

    def test_writes_a_durable_audit_entry_with_before_and_after(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        channel = CreateChannel(repo, audit).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        SetChannelStatus(repo, audit).execute(slug="coffee", active=False, actor="operator")

        status_calls = [call for call in audit.calls if call.action == "channel.status_changed"]
        assert len(status_calls) == 1
        call = status_calls[0]
        assert call.resource_id == str(channel.id)
        assert call.actor == "operator"
        assert call.changes == (FieldChange(field="is_active", before=True, after=False),)

    def test_a_no_op_status_change_is_not_audited(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        CreateChannel(repo, audit).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        SetChannelStatus(repo, audit).execute(slug="coffee", active=True)

        # The create was audited; the no-op activation added nothing.
        assert [call.action for call in audit.calls] == ["channel.created"]


class TestGetChannel:
    def test_returns_the_requested_channel(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        CreateChannel(repo, audit).execute(
            CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR")
        )

        channel = GetChannel(repo).execute(slug="coffee")

        assert channel.slug.value == "coffee"

    def test_raises_when_missing(self, repo: FakeChannelRepository) -> None:
        with pytest.raises(ChannelNotFoundError):
            GetChannel(repo).execute(slug="ghost")


class TestListChannels:
    def test_returns_all_channels_sorted_by_slug(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        create = CreateChannel(repo, audit)
        create.execute(CreateChannelCommand(name="Tea", slug="tea", currency="IRR"))
        create.execute(CreateChannelCommand(name="Coffee", slug="coffee", currency="IRR"))

        channels = ListChannels(repo).execute()

        assert [c.slug.value for c in channels] == ["coffee", "tea"]

    def test_can_filter_to_active_channels_only(
        self, repo: FakeChannelRepository, audit: FakeAuditRecorder
    ) -> None:
        create = CreateChannel(repo, audit)
        create.execute(CreateChannelCommand(name="Tea", slug="tea", currency="IRR"))
        create.execute(
            CreateChannelCommand(name="Draft", slug="draft", currency="IRR", is_active=False)
        )

        channels = ListChannels(repo).execute(only_active=True)

        assert [c.slug.value for c in channels] == ["tea"]
