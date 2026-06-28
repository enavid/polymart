"""Ports (interfaces) for the audit context.

The application layer depends only on these abstractions; concrete adapters (the
Django trail, a system clock) live in infrastructure and are injected at the
composition root, so the dependency rule keeps pointing inward.

Two levels of abstraction are exposed on purpose:

* ``AuditRecorder`` is the *high-level* seam other use cases depend on -- they say
  "record this change" without knowing about time or storage.
* ``AuditTrail`` and ``Clock`` are the *low-level* ports the default recorder is
  built from. Splitting them keeps each use case's dependency to a single, intent
  -revealing collaborator while staying fully testable against fakes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime

from src.domain.audit.entities import AuditEntry, FieldChange


class AuditTrail(ABC):
    """Append-only persistence boundary for audit entries."""

    @abstractmethod
    def record(self, entry: AuditEntry) -> None:
        """Durably append one entry. Never updates or deletes."""


class AuditQuery(ABC):
    """Read boundary for the audit trail (separate from the write port).

    Splitting read from write keeps the append-only writer free of query concerns
    and lets the reader evolve (pagination, projections) independently.
    """

    @abstractmethod
    def list_recent(
        self,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        action: str | None = None,
        limit: int,
    ) -> Sequence[AuditEntry]:
        """Return the most recent entries (newest first), optionally filtered."""


class Clock(ABC):
    """Source of the current time, injected so timestamps are testable.

    Each bounded context owns its own ``Clock`` port (the dependency rule keeps
    them decoupled); the trivial system adapter lives in infrastructure.
    """

    @abstractmethod
    def now(self) -> datetime:
        """Return the current timezone-aware time."""


class AuditRecorder(ABC):
    """The seam use cases depend on to record a change.

    Implementations stamp the time and assemble the ``AuditEntry``; callers supply
    only the business facts of what changed.
    """

    @abstractmethod
    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: Sequence[FieldChange] = (),
    ) -> None:
        """Record one change to the audit trail."""
