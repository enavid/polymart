"""Integration tests for the Django event publisher's after-commit delivery.

The publisher's whole reason for existing is *timing*: a domain event published inside a
use case's transaction must reach subscribers only if that transaction commits, so a
rolled-back order or payment never triggers a side effect. These tests drive real Django
transactions (``transaction=True``) to prove: delivery waits for commit, a rollback
discards the event, and a publish outside any transaction fires immediately. The structured
log is asserted to carry the event name without the money amount.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.db import transaction
from structlog.testing import capture_logs

from src.domain.order.events import OrderPlaced
from src.domain.shared.events import DomainEvent
from src.infrastructure.events.publisher import DjangoEventPublisher

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.integration]


def _order_placed() -> OrderPlaced:
    return OrderPlaced(
        occurred_at=datetime(2026, 7, 6, 12, 0, tzinfo=UTC),
        order_number="ORD-EVT001",
        owner="u:7",
        channel="ir-main",
        currency="IRR",
        total=Decimal("240000.00"),
        line_count=1,
    )


class TestAfterCommitDelivery:
    def test_delivers_to_subscribers_only_after_the_transaction_commits(self) -> None:
        received: list[DomainEvent] = []
        publisher = DjangoEventPublisher(subscribers=[received.append])
        event = _order_placed()

        with transaction.atomic():
            publisher.publish(event)
            # Still inside the transaction: nothing delivered yet.
            assert received == []
        # Committed: the subscriber now sees exactly the published event.
        assert received == [event]

    def test_discards_the_event_when_the_transaction_rolls_back(self) -> None:
        received: list[DomainEvent] = []
        publisher = DjangoEventPublisher(subscribers=[received.append])

        with pytest.raises(RuntimeError), transaction.atomic():
            publisher.publish(_order_placed())
            raise RuntimeError("boom")

        # A rolled-back transaction never fires the side effect.
        assert received == []

    def test_delivers_immediately_without_an_open_transaction(self) -> None:
        received: list[DomainEvent] = []
        publisher = DjangoEventPublisher(subscribers=[received.append])
        event = _order_placed()

        publisher.publish(event)

        assert received == [event]

    def test_delivers_to_every_subscriber_in_order(self) -> None:
        first: list[DomainEvent] = []
        second: list[DomainEvent] = []
        publisher = DjangoEventPublisher(subscribers=[first.append, second.append])
        event = _order_placed()

        publisher.publish(event)

        assert first == [event]
        assert second == [event]

    def test_logs_the_event_name_without_the_amount(self) -> None:
        publisher = DjangoEventPublisher()

        with capture_logs() as logs:
            publisher.publish(_order_placed())

        published = [entry for entry in logs if entry["event"] == "domain_event_published"]
        assert len(published) == 1
        entry = published[0]
        assert entry["event_name"] == "order.placed"
        assert entry["order_number"] == "ORD-EVT001"
        # The money amount and the raw owner never reach the log.
        assert "240000.00" not in str(entry)
        assert "owner" not in entry
