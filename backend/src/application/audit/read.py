"""Read use case for the audit trail: list recent entries with a safe limit.

Owns the application policy for *reading* the trail -- a sane default page size
and a hard ceiling so a caller can never ask for an unbounded scan -- over the
``AuditQuery`` port. No framework or transport detail leaks in here.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.audit.ports import AuditQuery
from src.domain.audit.entities import AuditEntry

# Paging policy. A modest default and a hard ceiling so the endpoint cannot be
# coerced into an unbounded table scan.
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class ListAuditEntries:
    """Return recent audit entries (newest first), optionally filtered."""

    def __init__(self, query: AuditQuery) -> None:
        self._query = query

    def execute(
        self,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        action: str | None = None,
        limit: int | None = None,
    ) -> Sequence[AuditEntry]:
        return self._query.list_recent(
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            limit=self._clamp(limit),
        )

    @staticmethod
    def _clamp(limit: int | None) -> int:
        if limit is None or limit < 1:
            return DEFAULT_LIMIT
        return min(limit, MAX_LIMIT)
