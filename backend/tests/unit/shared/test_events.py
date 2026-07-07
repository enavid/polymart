"""Unit tests for the domain-event value objects and their log projections.

Domain events are immutable facts that already happened. They carry everything a
subscriber might need (including money and the owner id), but their ``to_log`` projection
is deliberately narrow: it never leaks the amount (a money value) or the raw owner id
(a guest's owner embeds a bearer token), matching the money-safe logging convention the
use cases already follow.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.order.events import OrderPlaced
from src.domain.payment.events import PaymentCaptured
from src.domain.shared.events import DomainEvent

_OCCURRED_AT = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)


class TestDomainEventBase:
    def test_the_base_log_projection_is_empty(self) -> None:
        # A bare event (or one that does not override to_log) exposes no log fields.
        assert DomainEvent(occurred_at=_OCCURRED_AT).to_log() == {}


class TestOrderPlaced:
    def _event(self) -> OrderPlaced:
        return OrderPlaced(
            occurred_at=_OCCURRED_AT,
            order_number="ORD-ABC123",
            owner="g:secret-token",
            channel="ir-main",
            currency="IRR",
            total=Decimal("390000.00"),
            line_count=2,
        )

    def test_is_a_domain_event_with_a_stable_name(self) -> None:
        assert OrderPlaced.name == "order.placed"
        assert isinstance(self._event(), DomainEvent)

    def test_is_immutable(self) -> None:
        event = self._event()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.order_number = "ORD-OTHER1"  # type: ignore[misc]

    def test_to_log_omits_the_amount_and_the_raw_owner(self) -> None:
        fields = self._event().to_log()
        assert fields == {
            "order_number": "ORD-ABC123",
            "channel": "ir-main",
            "currency": "IRR",
            "line_count": 2,
        }
        # The money value and the raw (token-bearing) owner never reach the log.
        assert "total" not in fields
        assert "owner" not in fields
        assert "g:secret-token" not in fields.values()


class TestPaymentCaptured:
    def _event(self) -> PaymentCaptured:
        return PaymentCaptured(
            occurred_at=_OCCURRED_AT,
            payment_reference="PAY-ABC123",
            order_number="ORD-ABC123",
            owner="g:secret-token",
            method="online",
            amount=Decimal("390000.00"),
            currency="IRR",
        )

    def test_is_a_domain_event_with_a_stable_name(self) -> None:
        assert PaymentCaptured.name == "payment.captured"
        assert isinstance(self._event(), DomainEvent)

    def test_is_immutable(self) -> None:
        event = self._event()
        with pytest.raises(dataclasses.FrozenInstanceError):
            event.amount = Decimal("1.00")  # type: ignore[misc]

    def test_to_log_omits_the_amount_and_the_raw_owner(self) -> None:
        fields = self._event().to_log()
        assert fields == {
            "payment_reference": "PAY-ABC123",
            "order_number": "ORD-ABC123",
            "method": "online",
            "currency": "IRR",
        }
        assert "amount" not in fields
        assert "owner" not in fields
        assert "g:secret-token" not in fields.values()
