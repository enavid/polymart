"""Django ORM implementation of the audit query port (read-only)."""

from __future__ import annotations

from collections.abc import Sequence

from src.application.audit.ports import AuditQuery
from src.domain.audit.entities import AuditEntry
from src.infrastructure.audit.mappers import row_to_entry
from src.infrastructure.audit.models import AuditLogModel


class DjangoAuditReader(AuditQuery):
    """Read recent audit entries with the Django ORM, mapping rows to entities."""

    def list_recent(
        self,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        action: str | None = None,
        limit: int,
    ) -> Sequence[AuditEntry]:
        queryset = AuditLogModel.objects.all()
        if resource_type is not None:
            queryset = queryset.filter(resource_type=resource_type)
        if resource_id is not None:
            queryset = queryset.filter(resource_id=resource_id)
        if action is not None:
            queryset = queryset.filter(action=action)
        # The model's default ordering is newest-first; slice applies the limit in
        # SQL so the database never returns more rows than asked for.
        return [row_to_entry(row) for row in queryset[:limit]]
