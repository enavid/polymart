"""Composition root for the audit slice.

Wires the concrete trail + clock into the default recorder. Other slices import
``build_audit_recorder`` to obtain the ``AuditRecorder`` their use cases depend
on, never the infrastructure adapters directly.
"""

from __future__ import annotations

from src.application.audit.ports import AuditRecorder
from src.application.audit.recorder import PersistentAuditRecorder
from src.infrastructure.audit.clock import SystemClock
from src.infrastructure.audit.trail import DjangoAuditTrail


def build_audit_recorder() -> AuditRecorder:
    return PersistentAuditRecorder(DjangoAuditTrail(), SystemClock())
