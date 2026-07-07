"""Composition root for the event bus.

The one place that assembles the concrete ``EventPublisher`` and registers its subscribers.
Use cases receive the publisher through this factory and never see the infrastructure. There
are no platform subscribers yet -- this slice delivers the *publication* seam -- so
notification/webhook/fulfilment handlers register here in their own phases without any use
case changing.
"""

from __future__ import annotations

from src.infrastructure.events.publisher import DjangoEventPublisher


def build_event_publisher() -> DjangoEventPublisher:
    """The event publisher wired into the money-moving use cases (no subscribers yet)."""
    return DjangoEventPublisher()
