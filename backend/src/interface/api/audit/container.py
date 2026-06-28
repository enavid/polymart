"""Composition root for the audit slice.

Wires the concrete trail + clock into the default recorder. Other slices import
``build_audit_recorder`` to obtain the ``AuditRecorder`` their use cases depend
on, never the infrastructure adapters directly.
"""

from __future__ import annotations

from src.application.audit.ports import AuditRecorder
from src.application.audit.read import ListAuditEntries
from src.application.audit.recorder import PersistentAuditRecorder
from src.infrastructure.audit.clock import SystemClock
from src.infrastructure.audit.reader import DjangoAuditReader
from src.infrastructure.audit.trail import DjangoAuditTrail


def build_audit_recorder() -> AuditRecorder:
    return PersistentAuditRecorder(DjangoAuditTrail(), SystemClock())


def build_list_audit_entries() -> ListAuditEntries:
    return ListAuditEntries(DjangoAuditReader())
