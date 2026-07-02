"""Unit tests for the Order aggregate and its state machine (pure, no framework)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.order.entities import Order, OrderLine
from src.domain.order.exceptions import (
    EmptyOrderError,
    IllegalOrderTransitionError,
    OrderCurrencyMismatchError,
    OrderTotalMismatchError,
)
from src.domain.order.value_objects import (
    ChannelRef,
    Money,
    OrderNumber,
    OrderQuantity,
    OrderStatus,
    ShippingAddress,
    Sku,
)


def _money(amount: str, currency: str = "IRR") -> Money:
    return Money(amount=Decimal(amount), currency=currency)


def _line(sku: str, qty: int, unit: str) -> OrderLine:
    unit_price = _money(unit)
    quantity = OrderQuantity(qty)
    return OrderLine(
        sku=Sku(sku),
        quantity=quantity,
        unit_price=unit_price,
        line_total=unit_price.times(quantity),
    )


def _shipping_address(**overrides: str | None) -> ShippingAddress:
    fields = {
        "recipient_name": "Sara Ahmadi",
        "phone_number": "+989123456789",
        "province": "Tehran",
        "city": "Tehran",
        "postal_code": "1234567890",
        "line1": "Valiasr St, No. 1",
        "line2": None,
        **overrides,
    }
    return ShippingAddress(**fields)  # type: ignore[arg-type]


def _order(lines: tuple[OrderLine, ...], status: OrderStatus = OrderStatus.PENDING) -> Order:
    total = Money.zero("IRR")
    for line in lines:
        total = total.add(line.line_total)
    return Order(
        number=OrderNumber("ORD-ABC123"),
        owner="7",
        channel=ChannelRef("ir-main"),
        currency="IRR",
        lines=lines,
        total=total,
        status=status,
        placed_at=datetime(2026, 7, 2, tzinfo=UTC),
        shipping_address=_shipping_address(),
    )


class TestOrderLine:
    def test_accepts_a_consistent_snapshot(self) -> None:
        line = _line("HB-250", 2, "120000.00")
        assert line.line_total.amount == Decimal("240000.00")

    def test_rejects_a_total_that_is_not_unit_times_quantity(self) -> None:
        with pytest.raises(OrderTotalMismatchError):
            OrderLine(
                sku=Sku("HB-250"),
                quantity=OrderQuantity(2),
                unit_price=_money("120000.00"),
                line_total=_money("999.00"),
            )

    def test_rejects_a_currency_mismatch_between_unit_and_total(self) -> None:
        with pytest.raises(OrderCurrencyMismatchError):
            OrderLine(
                sku=Sku("HB-250"),
                quantity=OrderQuantity(1),
                unit_price=_money("120000.00", "IRR"),
                line_total=_money("120000.00", "USD"),
            )


class TestOrderInvariants:
    def test_builds_with_a_matching_total(self) -> None:
        order = _order((_line("HB-250", 2, "120000.00"), _line("DR-250", 1, "150000.00")))
        assert order.total.amount == Decimal("390000.00")
        assert order.status is OrderStatus.PENDING

    def test_carries_the_captured_shipping_address(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),))
        assert order.shipping_address.recipient_name == "Sara Ahmadi"
        assert order.shipping_address.city == "Tehran"

    def test_a_status_transition_preserves_the_shipping_address(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),))
        moved = order.transition_to(OrderStatus.PAID)
        assert moved.shipping_address == order.shipping_address

    def test_rejects_an_order_with_no_lines(self) -> None:
        with pytest.raises(EmptyOrderError):
            _order(())

    def test_rejects_a_total_that_does_not_match_the_lines(self) -> None:
        line = _line("HB-250", 1, "120000.00")
        with pytest.raises(OrderTotalMismatchError):
            Order(
                number=OrderNumber("ORD-ABC123"),
                owner="7",
                channel=ChannelRef("ir-main"),
                currency="IRR",
                lines=(line,),
                total=_money("999.00"),
                status=OrderStatus.PENDING,
                placed_at=datetime(2026, 7, 2, tzinfo=UTC),
                shipping_address=_shipping_address(),
            )

    def test_rejects_a_line_in_another_currency(self) -> None:
        line = OrderLine(
            sku=Sku("HB-250"),
            quantity=OrderQuantity(1),
            unit_price=_money("120000.00", "USD"),
            line_total=_money("120000.00", "USD"),
        )
        with pytest.raises(OrderCurrencyMismatchError):
            Order(
                number=OrderNumber("ORD-ABC123"),
                owner="7",
                channel=ChannelRef("ir-main"),
                currency="IRR",
                lines=(line,),
                total=_money("120000.00", "IRR"),
                status=OrderStatus.PENDING,
                placed_at=datetime(2026, 7, 2, tzinfo=UTC),
                shipping_address=_shipping_address(),
            )


class TestStateMachine:
    def test_pending_can_transition_to_paid(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),))
        assert order.transition_to(OrderStatus.PAID).status is OrderStatus.PAID

    def test_pending_can_be_cancelled(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),))
        assert order.cancel().status is OrderStatus.CANCELLED

    def test_paid_can_transition_to_fulfilled(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),), status=OrderStatus.PAID)
        assert order.transition_to(OrderStatus.FULFILLED).status is OrderStatus.FULFILLED

    def test_transition_returns_a_new_immutable_instance(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),))
        moved = order.transition_to(OrderStatus.PAID)
        # The original is unchanged (aggregate is frozen); a copy carries the new status.
        assert order.status is OrderStatus.PENDING
        assert moved is not order

    @pytest.mark.parametrize(
        ("start", "target"),
        [
            (OrderStatus.PENDING, OrderStatus.FULFILLED),
            (OrderStatus.FULFILLED, OrderStatus.PAID),
            (OrderStatus.CANCELLED, OrderStatus.PAID),
            (OrderStatus.PAID, OrderStatus.PENDING),
        ],
    )
    def test_rejects_an_illegal_transition(self, start: OrderStatus, target: OrderStatus) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),), status=start)
        with pytest.raises(IllegalOrderTransitionError):
            order.transition_to(target)

    def test_cancelling_a_fulfilled_order_is_illegal(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),), status=OrderStatus.FULFILLED)
        with pytest.raises(IllegalOrderTransitionError):
            order.cancel()
