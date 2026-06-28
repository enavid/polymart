"""Unit tests for the PersistentAuditRecorder application service.

The recorder is the seam other use cases depend on. It stamps the time from an
injected clock and forwards a fully-formed ``AuditEntry`` to the trail port --
both faked here, so the test needs neither a database nor a real clock.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.application.audit.ports import AuditTrail
from src.application.audit.recorder import PersistentAuditRecorder
from src.domain.audit.entities import AuditEntry, FieldChange

_FROZEN = datetime(2026, 6, 28, 9, 30, tzinfo=UTC)


class FakeAuditTrail(AuditTrail):
    """Captures recorded entries in memory instead of persisting them."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


class FixedClock:
    """A clock pinned to a known instant so timestamps are assertable."""

    def now(self) -> datetime:
        return _FROZEN


def _recorder(trail: AuditTrail) -> PersistentAuditRecorder:
    return PersistentAuditRecorder(trail, FixedClock())


class TestPersistentAuditRecorder:
    def test_builds_and_forwards_an_entry_with_the_clock_timestamp(self) -> None:
        trail = FakeAuditTrail()

        _recorder(trail).record(
            action="channel.status_changed",
            resource_type="channel",
            resource_id="7",
            actor="42",
            changes=[FieldChange(field="is_active", before=True, after=False)],
        )

        assert len(trail.entries) == 1
        entry = trail.entries[0]
        assert entry.action == "channel.status_changed"
        assert entry.resource_id == "7"
        assert entry.actor == "42"
        assert entry.occurred_at == _FROZEN
        assert entry.changes == (FieldChange(field="is_active", before=True, after=False),)

    def test_actor_and_changes_are_optional(self) -> None:
        trail = FakeAuditTrail()

        _recorder(trail).record(action="channel.created", resource_type="channel", resource_id="1")

        entry = trail.entries[0]
        assert entry.actor is None
        assert entry.changes == ()

    def test_normalizes_a_changes_sequence_to_an_immutable_tuple(self) -> None:
        # Callers may pass any sequence; the stored entry must be immutable.
        trail = FakeAuditTrail()

        _recorder(trail).record(
            action="channel.created",
            resource_type="channel",
            resource_id="1",
            changes=[FieldChange(field="slug", after="coffee")],
        )

        assert isinstance(trail.entries[0].changes, tuple)
