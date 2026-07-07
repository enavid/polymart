"""The domain-event base -- a tiny shared kernel every context's events build on.

A domain event is an immutable statement that *something already happened* (an order was
placed, a payment was captured). Use cases publish events through the ``EventPublisher``
port so side effects (notifications, webhooks, fulfilment) can react without the use case
depending on them -- the event bus is the seam.

The base carries only what every event shares: the instant it occurred and a stable
``name`` used on the bus and in logs. Each event exposes a ``to_log`` projection of the
fields that are safe to write to the structured logs -- deliberately never the amount (a
money value) or the raw owner id (a guest owner embeds a bearer token), mirroring the
money-safe logging the use cases already follow.

Pure Python -- no Django, no DRF, no ORM.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar


@dataclass(frozen=True)
class DomainEvent:
    """Immutable base for a fact that already happened in the domain.

    Subclasses set ``name`` (a stable, dotted identifier such as ``order.placed``) and add
    their own fields. ``occurred_at`` is tz-aware. Subclasses override ``to_log`` to expose
    only the fields that are safe to log.
    """

    # A stable event name, set by each subclass; not a dataclass field.
    name: ClassVar[str]

    occurred_at: datetime

    def to_log(self) -> dict[str, object]:
        """Return the fields safe to write to the structured logs (no money, no PII).

        The default is empty; each event overrides it with its own non-sensitive fields.
        """
        return {}
