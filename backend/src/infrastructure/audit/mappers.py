"""Mapping between the audit domain entity and its ORM representation."""

from __future__ import annotations

from src.domain.audit.entities import AuditValue, FieldChange


def changes_to_json(changes: tuple[FieldChange, ...]) -> dict[str, dict[str, AuditValue]]:
    """Project per-field changes onto the stored JSON shape.

    ``({field: {"before": ..., "after": ...}})`` -- a flat, queryable mapping.
    """
    return {change.field: {"before": change.before, "after": change.after} for change in changes}
