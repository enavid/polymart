"""The default audit recorder: stamp the time, build the entry, persist it.

Pure orchestration over the ``Clock`` and ``AuditTrail`` ports -- no framework
imports -- so it is unit-testable against fakes. Other use cases depend on the
``AuditRecorder`` abstraction, not on this concrete class.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from src.application.audit.ports import AuditRecorder, AuditTrail, Clock
from src.domain.audit.entities import AuditEntry, FieldChange

logger = structlog.get_logger(__name__)


class PersistentAuditRecorder(AuditRecorder):
    """Assemble an ``AuditEntry`` from a clock + business facts and persist it."""

    def __init__(self, trail: AuditTrail, clock: Clock) -> None:
        self._trail = trail
        self._clock = clock

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: Sequence[FieldChange] = (),
    ) -> None:
        entry = AuditEntry(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            occurred_at=self._clock.now(),
            actor=actor,
            changes=tuple(changes),
        )
        self._trail.record(entry)
        # Safe to log: action/resource are not PII and actor is a stable id, not
        # the phone number. The change values themselves are never logged here.
        logger.debug(
            "audit_entry_recorded",
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
        )
