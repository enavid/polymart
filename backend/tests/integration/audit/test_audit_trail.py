"""Integration tests for the Django audit trail (persistence path + DB).

These assert that an ``AuditEntry`` round-trips into an ``audit_log`` row, that
the per-field before/after changes are stored as the agreed JSON shape, and that
the trail is append-only.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.domain.audit.entities import AuditEntry, FieldChange
from src.infrastructure.audit.models import AuditLogModel
from src.infrastructure.audit.trail import DjangoAuditTrail

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_NOW = datetime(2026, 6, 28, 12, 0, tzinfo=UTC)


def _entry(**overrides: object) -> AuditEntry:
    defaults: dict[str, object] = {
        "action": "channel.status_changed",
        "resource_type": "channel",
        "resource_id": "7",
        "occurred_at": _NOW,
        "actor": "42",
        "changes": (FieldChange(field="is_active", before=True, after=False),),
    }
    defaults.update(overrides)
    return AuditEntry(**defaults)  # type: ignore[arg-type]


class TestDjangoAuditTrail:
    def test_records_an_entry_as_a_row(self) -> None:
        DjangoAuditTrail().record(_entry())

        row = AuditLogModel.objects.get()
        assert row.action == "channel.status_changed"
        assert row.resource_type == "channel"
        assert row.resource_id == "7"
        assert row.actor == "42"
        assert row.occurred_at == _NOW
        assert str(row) == f"audit:channel.status_changed:{row.pk}"

    def test_stores_changes_as_before_after_json(self) -> None:
        DjangoAuditTrail().record(_entry())

        row = AuditLogModel.objects.get()
        assert row.changes == {"is_active": {"before": True, "after": False}}

    def test_a_system_entry_has_a_null_actor(self) -> None:
        DjangoAuditTrail().record(_entry(actor=None, changes=()))

        row = AuditLogModel.objects.get()
        assert row.actor is None
        assert row.changes == {}

    def test_is_append_only_each_record_adds_a_row(self) -> None:
        trail = DjangoAuditTrail()

        trail.record(_entry(resource_id="1"))
        trail.record(_entry(resource_id="2"))

        assert AuditLogModel.objects.count() == 2
        assert {row.resource_id for row in AuditLogModel.objects.all()} == {"1", "2"}
