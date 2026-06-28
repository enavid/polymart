"""Django ORM implementation of the audit trail port (append-only)."""

from __future__ import annotations

from src.application.audit.ports import AuditTrail
from src.domain.audit.entities import AuditEntry
from src.infrastructure.audit.mappers import changes_to_json
from src.infrastructure.audit.models import AuditLogModel


class DjangoAuditTrail(AuditTrail):
    """Persist audit entries with the Django ORM. Inserts only -- never mutates."""

    def record(self, entry: AuditEntry) -> None:
        # A single create() is atomic; the trail is append-only, so there is no
        # read-modify-write to guard against.
        AuditLogModel.objects.create(
            action=entry.action,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
            actor=entry.actor,
            changes=changes_to_json(entry.changes),
            occurred_at=entry.occurred_at,
        )
