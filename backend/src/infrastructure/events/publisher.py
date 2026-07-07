"""The Django-backed event publisher: an in-process bus that delivers *after commit*.

This is the concrete ``EventPublisher`` wired at the composition root. It holds the
registered subscribers and, crucially, defers delivery to ``transaction.on_commit`` -- so a
domain event published inside a use case's ``atomic()`` block reaches subscribers only if
that transaction actually commits. A rolled-back order or payment (an oversell, a failed
capture) therefore never triggers a side effect. Outside any atomic block ``on_commit`` runs
the callback immediately, so a publish is never silently lost.

Every delivered event is also written to the structured logs (``domain_event_published``)
through the event's own ``to_log`` projection, which excludes the amount and the raw owner
id -- observability without leaking money or a guest's bearer token. Subscribers are plain
callables registered at the composition root; there are none in the platform yet (this slice
delivers the *publication* seam), and notification/webhook/fulfilment handlers plug in here
without the use cases changing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import structlog
from django.db import transaction

from src.application.shared.events import EventPublisher
from src.domain.shared.events import DomainEvent

logger = structlog.get_logger(__name__)

# A subscriber reacts to a delivered event; it must not raise (a failing side effect must
# not break an already-committed transaction). Registered at the composition root.
Subscriber = Callable[[DomainEvent], None]


class DjangoEventPublisher(EventPublisher):
    """Publishes events to registered subscribers once the surrounding transaction commits."""

    def __init__(self, subscribers: Sequence[Subscriber] = ()) -> None:
        self._subscribers = tuple(subscribers)

    def publish(self, event: DomainEvent) -> None:
        # Deliver after commit: if the caller's transaction rolls back, the callback is
        # discarded and no subscriber runs. With no open transaction it fires immediately.
        transaction.on_commit(lambda: self._deliver(event))

    def _deliver(self, event: DomainEvent) -> None:
        # ``event_name`` (not ``event``) -- structlog binds the log message to the ``event``
        # key, so the domain event's own name goes under a distinct field.
        logger.info("domain_event_published", event_name=event.name, **event.to_log())
        for subscriber in self._subscribers:
            subscriber(event)
