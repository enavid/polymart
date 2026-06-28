"""Mapping between the audit domain entity and its ORM representation."""

from __future__ import annotations

from src.domain.audit.entities import AuditEntry, AuditValue, FieldChange
from src.infrastructure.audit.models import AuditLogModel


def changes_to_json(changes: tuple[FieldChange, ...]) -> dict[str, dict[str, AuditValue]]:
    """Project per-field changes onto the stored JSON shape.

    ``({field: {"before": ..., "after": ...}})`` -- a flat, queryable mapping.
    """
    return {change.field: {"before": change.before, "after": change.after} for change in changes}


def changes_from_json(stored: dict[str, dict[str, AuditValue]]) -> tuple[FieldChange, ...]:
    """Reconstruct the per-field changes from their stored JSON shape."""
    return tuple(
        FieldChange(field=field, before=values.get("before"), after=values.get("after"))
        for field, values in stored.items()
    )


def row_to_entry(row: AuditLogModel) -> AuditEntry:
    """Map a stored row back to the domain entity (for the read path)."""
    return AuditEntry(
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        occurred_at=row.occurred_at,
        actor=row.actor,
        changes=changes_from_json(row.changes),
    )
