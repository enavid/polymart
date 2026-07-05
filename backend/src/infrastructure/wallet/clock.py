"""System clock adapter for the wallet ``Clock`` port.

A deliberate twin of the payment/order/audit clocks: each bounded context owns its own
``Clock`` port so the application layers stay decoupled, and the adapter is a trivial
one-liner returning a timezone-aware instant.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.application.wallet.ports import Clock


class SystemClock(Clock):
    """The real wall clock, in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)
