"""System clock adapter for the audit ``Clock`` port."""

from __future__ import annotations

from datetime import UTC, datetime

from src.application.audit.ports import Clock


class SystemClock(Clock):
    """The real wall clock, in UTC.

    A deliberate twin of the identity clock: each bounded context owns its own
    ``Clock`` port so the application layers stay decoupled, and the adapter is a
    trivial one-liner.
    """

    def now(self) -> datetime:
        return datetime.now(UTC)
