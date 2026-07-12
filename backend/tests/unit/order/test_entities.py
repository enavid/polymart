"""Unit tests for the Order aggregate and its state machine (pure, no framework)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.domain.order.entities import Order, OrderLine
from src.domain.order.exceptions import (
    DuplicateOrderLineError,
    EmptyOrderError,
    IllegalOrderTransitionError,
    InvalidFulfillmentError,
    OrderCurrencyMismatchError,
    OrderTotalMismatchError,
)
from src.domain.order.value_objects import (
    CapturedShipping,
    CapturedTax,
    ChannelRef,
    Fulfillment,
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


def _order(
    lines: tuple[OrderLine, ...],
    status: OrderStatus = OrderStatus.PENDING,
    shipping: CapturedShipping | None = None,
    tax: CapturedTax | None = None,
) -> Order:
    total = Money.zero("IRR")
    for line in lines:
        total = total.add(line.line_total)
    if shipping is not None:
        total = total.add(shipping.cost)
    if tax is not None:
        total = total.add(tax.amount)
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
        shipping=shipping,
        tax=tax,
    )


def _shipping(amount: str = "50000.00", currency: str = "IRR") -> CapturedShipping:
    return CapturedShipping(
        method_code="standard", method_name="Standard post", cost=_money(amount, currency)
    )


def _tax(rate: str = "9", amount: str = "15300.00", currency: str = "IRR") -> CapturedTax:
    return CapturedTax(rate=Decimal(rate), amount=_money(amount, currency))


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

    def test_rejects_the_same_variant_on_two_lines(self) -> None:
        # A manual order takes an arbitrary line list; a variant must appear at most
        # once (as the persisted unique (order, sku) constraint also enforces).
        with pytest.raises(DuplicateOrderLineError):
            _order((_line("HB-250", 1, "120000.00"), _line("HB-250", 2, "120000.00")))

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


class TestOrderShipping:
    def test_total_includes_the_shipping_cost(self) -> None:
        order = _order((_line("HB-250", 2, "120000.00"),), shipping=_shipping("50000.00"))
        # subtotal 240000 + shipping 50000 = 290000 grand total.
        assert order.items_subtotal.amount == Decimal("240000.00")
        assert order.shipping_cost.amount == Decimal("50000.00")
        assert order.total.amount == Decimal("290000.00")

    def test_no_shipping_reports_a_zero_cost_and_subtotal_equals_total(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),))
        assert order.shipping is None
        assert order.shipping_cost.amount == Decimal("0")
        assert order.total.amount == order.items_subtotal.amount

    def test_a_free_shipping_method_is_valid(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),), shipping=_shipping("0"))
        assert order.total.amount == Decimal("120000.00")
        assert order.shipping is not None
        assert order.shipping.method_code == "standard"

    def test_rejects_a_total_that_omits_the_shipping_cost(self) -> None:
        line = _line("HB-250", 1, "120000.00")
        with pytest.raises(OrderTotalMismatchError):
            Order(
                number=OrderNumber("ORD-ABC123"),
                owner="7",
                channel=ChannelRef("ir-main"),
                currency="IRR",
                lines=(line,),
                total=_money("120000.00"),  # subtotal only -- shipping not added
                status=OrderStatus.PENDING,
                placed_at=datetime(2026, 7, 2, tzinfo=UTC),
                shipping_address=_shipping_address(),
                shipping=_shipping("50000.00"),
            )

    def test_rejects_shipping_in_another_currency(self) -> None:
        line = _line("HB-250", 1, "120000.00")
        with pytest.raises(OrderCurrencyMismatchError):
            Order(
                number=OrderNumber("ORD-ABC123"),
                owner="7",
                channel=ChannelRef("ir-main"),
                currency="IRR",
                lines=(line,),
                total=_money("170000.00"),
                status=OrderStatus.PENDING,
                placed_at=datetime(2026, 7, 2, tzinfo=UTC),
                shipping_address=_shipping_address(),
                shipping=_shipping("50000.00", "USD"),
            )

    def test_a_transition_preserves_the_captured_shipping(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),), shipping=_shipping("50000.00"))
        moved = order.transition_to(OrderStatus.PAID)
        assert moved.shipping == order.shipping


class TestOrderTax:
    def test_total_includes_the_tax_amount(self) -> None:
        # subtotal 240000 + shipping 50000 = 290000 base; 9% tax = 26100 -> total 316100.
        order = _order(
            (_line("HB-250", 2, "120000.00"),),
            shipping=_shipping("50000.00"),
            tax=_tax("9", "26100.00"),
        )
        assert order.items_subtotal.amount == Decimal("240000.00")
        assert order.shipping_cost.amount == Decimal("50000.00")
        assert order.tax_amount.amount == Decimal("26100.00")
        assert order.total.amount == Decimal("316100.00")

    def test_tax_on_goods_only_when_no_shipping(self) -> None:
        # subtotal 120000, no shipping; 9% tax = 10800 -> total 130800.
        order = _order((_line("HB-250", 1, "120000.00"),), tax=_tax("9", "10800.00"))
        assert order.shipping is None
        assert order.tax_amount.amount == Decimal("10800.00")
        assert order.total.amount == Decimal("130800.00")

    def test_no_tax_reports_a_zero_amount(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),))
        assert order.tax is None
        assert order.tax_amount.amount == Decimal("0")

    def test_a_zero_amount_tax_line_is_valid(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),), tax=_tax("0", "0"))
        assert order.tax is not None
        assert order.tax.rate == Decimal("0")
        assert order.total.amount == Decimal("120000.00")

    def test_rejects_a_total_that_omits_the_tax(self) -> None:
        line = _line("HB-250", 1, "120000.00")
        with pytest.raises(OrderTotalMismatchError):
            Order(
                number=OrderNumber("ORD-ABC123"),
                owner="7",
                channel=ChannelRef("ir-main"),
                currency="IRR",
                lines=(line,),
                total=_money("120000.00"),  # subtotal only -- tax not added
                status=OrderStatus.PENDING,
                placed_at=datetime(2026, 7, 2, tzinfo=UTC),
                shipping_address=_shipping_address(),
                tax=_tax("9", "10800.00"),
            )

    def test_rejects_tax_in_another_currency(self) -> None:
        line = _line("HB-250", 1, "120000.00")
        with pytest.raises(OrderCurrencyMismatchError):
            Order(
                number=OrderNumber("ORD-ABC123"),
                owner="7",
                channel=ChannelRef("ir-main"),
                currency="IRR",
                lines=(line,),
                total=_money("130800.00"),
                status=OrderStatus.PENDING,
                placed_at=datetime(2026, 7, 2, tzinfo=UTC),
                shipping_address=_shipping_address(),
                tax=_tax("9", "10800.00", "USD"),
            )

    def test_total_includes_both_shipping_and_tax_together(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),), shipping=_shipping("50000.00"))
        assert order.total.amount == Decimal("170000.00")

    def test_a_transition_preserves_the_captured_tax(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),), tax=_tax("9", "10800.00"))
        moved = order.transition_to(OrderStatus.PAID)
        assert moved.tax == order.tax


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


def _pickup_shipping() -> CapturedShipping:
    return CapturedShipping(
        method_code="pickup", method_name="In-store pickup", cost=_money("0"), is_pickup=True
    )


class TestFulfillmentValueObject:
    def test_accepts_a_carrier_and_tracking(self) -> None:
        f = Fulfillment(carrier="  Post ", tracking_number=" TRK-1 ", tracking_url=" http://t ")
        # Whitespace is trimmed at the edge.
        assert f.carrier == "Post"
        assert f.tracking_number == "TRK-1"
        assert f.tracking_url == "http://t"

    def test_tracking_url_is_optional(self) -> None:
        assert Fulfillment(carrier="Post", tracking_number="TRK-1").tracking_url is None

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_rejects_a_blank_carrier(self, bad: str) -> None:
        with pytest.raises(InvalidFulfillmentError):
            Fulfillment(carrier=bad, tracking_number="TRK-1")

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_rejects_a_blank_tracking_number(self, bad: str) -> None:
        with pytest.raises(InvalidFulfillmentError):
            Fulfillment(carrier="Post", tracking_number=bad)


class TestShipOrder:
    def test_ship_captures_fulfillment_and_moves_to_fulfilled(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),), status=OrderStatus.PAID)
        shipped = order.ship(Fulfillment(carrier="Post", tracking_number="TRK-1"))
        assert shipped.status is OrderStatus.FULFILLED
        assert shipped.fulfillment is not None
        assert shipped.fulfillment.carrier == "Post"
        # Immutable: the original is untouched.
        assert order.status is OrderStatus.PAID
        assert order.fulfillment is None

    def test_ship_is_illegal_from_pending(self) -> None:
        order = _order((_line("HB-250", 1, "120000.00"),), status=OrderStatus.PENDING)
        with pytest.raises(IllegalOrderTransitionError):
            order.ship(Fulfillment(carrier="Post", tracking_number="TRK-1"))


class TestPickupLifecycle:
    def test_paid_to_ready_to_picked_up(self) -> None:
        order = _order(
            (_line("HB-250", 1, "120000.00"),),
            status=OrderStatus.PAID,
            shipping=_pickup_shipping(),
        )
        ready = order.mark_ready_for_pickup()
        assert ready.status is OrderStatus.READY_FOR_PICKUP
        picked = ready.confirm_pickup()
        assert picked.status is OrderStatus.PICKED_UP

    def test_confirm_pickup_before_ready_is_illegal(self) -> None:
        order = _order(
            (_line("HB-250", 1, "120000.00"),),
            status=OrderStatus.PAID,
            shipping=_pickup_shipping(),
        )
        with pytest.raises(IllegalOrderTransitionError):
            order.confirm_pickup()

    def test_a_pickup_order_needs_no_shipping_address(self) -> None:
        # A pickup order captures no address; the aggregate accepts shipping_address=None.
        line = _line("HB-250", 1, "120000.00")
        order = Order(
            number=OrderNumber("ORD-PICKUP1"),
            owner="7",
            channel=ChannelRef("ir-main"),
            currency="IRR",
            lines=(line,),
            total=line.line_total,
            status=OrderStatus.PENDING,
            placed_at=datetime(2026, 7, 2, tzinfo=UTC),
            shipping_address=None,
            shipping=_pickup_shipping(),
        )
        assert order.shipping_address is None
        assert order.shipping is not None and order.shipping.is_pickup
