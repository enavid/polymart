"""The event-publishing port -- the seam use cases publish domain events through.

A use case announces a fact (an order was placed, a payment was captured) by publishing a
``DomainEvent`` to this port; it never knows who, if anyone, reacts. Subscribers
(notifications, webhooks, fulfilment) are wired to the concrete adapter at the composition
root, keeping the dependency rule pointing inward -- the application layer depends only on
this abstraction.

*When* an event is delivered is deliberately left to the adapter: the money-moving use
cases publish inside their ``UnitOfWork.atomic()`` block, and the Django adapter defers
delivery until that transaction commits, so a rolled-back order or payment never triggers a
side effect. A fake publisher used in unit tests may deliver immediately; the port makes no
promise either way.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.shared.events import DomainEvent


class EventPublisher(ABC):
    """Publishes domain events to whatever has subscribed (the event bus seam)."""

    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        """Publish one domain event. Delivery timing is the adapter's concern."""
