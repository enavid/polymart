"""Audit domain entities: a single, self-validating record of a change.

This is pure Python -- only the standard library, no Django/DRF/ORM. Any bounded
context can emit an ``AuditEntry`` (who/when/what changed) without depending on
how it is stored.

The "what changed" is a tuple of ``FieldChange`` value objects, each holding the
before/after of one field. A creation has only "after" values; a status change
has both. Values are restricted to JSON-serialisable scalars so persistence is a
trivial projection and the trail never accidentally captures rich objects (or the
PII they might carry).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from src.domain.audit.exceptions import InvalidAuditEntryError

# The scalar values an audited field may take. Deliberately narrow: no nested
# structures, so a change is always a flat, greppable before/after pair.
AuditValue = str | bool | int | None

# A lowercase identifier (letter first): field names, resource types.
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# A dotted, namespaced event name, e.g. "channel.status_changed", so the trail is
# greppable by area (every channel event starts with "channel.").
_ACTION_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


@dataclass(frozen=True)
class FieldChange:
    """The before/after of one field. ``before`` is ``None`` for a creation."""

    field: str
    before: AuditValue = None
    after: AuditValue = None

    def __post_init__(self) -> None:
        if not _IDENTIFIER_RE.match(self.field):
            raise InvalidAuditEntryError(f"invalid change field: {self.field!r}")


@dataclass(frozen=True)
class AuditEntry:
    """One immutable audit record: who did what to which resource, and when."""

    action: str
    resource_type: str
    resource_id: str
    occurred_at: datetime
    actor: str | None = None
    changes: tuple[FieldChange, ...] = ()

    def __post_init__(self) -> None:
        if not _ACTION_RE.match(self.action):
            raise InvalidAuditEntryError(f"invalid action: {self.action!r}")
        if not _IDENTIFIER_RE.match(self.resource_type):
            raise InvalidAuditEntryError(f"invalid resource_type: {self.resource_type!r}")
        if not self.resource_id.strip():
            raise InvalidAuditEntryError("resource_id must not be blank")
        if self.actor is not None and not self.actor.strip():
            raise InvalidAuditEntryError("actor, when present, must not be blank")
        # A naive timestamp is ambiguous across zones; an audit trail cannot afford
        # that, so only tz-aware instants are accepted.
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise InvalidAuditEntryError("occurred_at must be a timezone-aware datetime")
