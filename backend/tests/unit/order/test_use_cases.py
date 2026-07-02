"""Unit tests for the order use cases against fakes (no DB, no framework).

These exercise the orchestration: price capture, atomic stock deduction and rollback,
audit recording, owner-scoping, pagination bounds, and the cancel/restock flow. The
fakes stand in for the Django adapters wired at the composition root.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.order.ports import (
    CartForCheckout,
    ChannelReader,
    CheckoutLine,
    Clock,
    Inventory,
    OrderNumberGenerator,
    OrderRepository,
    PricingReader,
    UnitOfWork,
)
from src.application.order.use_cases import (
    CancelMyOrder,
    CancelMyOrderCommand,
    GetMyOrder,
    InvalidOrderPageError,
    ListMyOrders,
    ListMyOrdersQuery,
    PlaceOrder,
    PlaceOrderCommand,
)
from src.domain.audit.entities import FieldChange
from src.domain.order.entities import Order
from src.domain.order.exceptions import (
    EmptyCartError,
    OrderNotCancellableError,
    OrderNotFoundError,
    OutOfStockError,
    UnknownChannelError,
    VariantNotPurchasableError,
)
from src.domain.order.value_objects import Money, OrderNumber, OrderStatus

# --- Fakes ---------------------------------------------------------------


class FakeUnitOfWork(UnitOfWork):
    """Records whether the transaction committed or rolled back.

    ``atomic`` yields normally and, on an exception, re-raises after marking a
    rollback -- so a use case that fails mid-way is observed to have "rolled back"
    without any real database.
    """

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    @contextmanager
    def atomic(self) -> Iterator[None]:
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise
        self.committed = True


class FakeCart(CartForCheckout):
    def __init__(self, items: tuple[CheckoutLine, ...]) -> None:
        self._items = items
        self.cleared = False

    def line_items(self, owner: str, channel: str) -> tuple[CheckoutLine, ...]:
        return self._items

    def clear(self, owner: str, channel: str) -> None:
        self.cleared = True
        self._items = ()


class FakePricing(PricingReader):
    def __init__(self, prices: dict[str, Money]) -> None:
        self._prices = prices

    def price_of(self, sku: str, channel: str) -> Money | None:
        return self._prices.get(sku)


class FakeChannels(ChannelReader):
    def __init__(self, currency: str | None) -> None:
        self._currency = currency

    def currency_of(self, channel: str) -> str | None:
        return self._currency


class FakeInventory(Inventory):
    def __init__(self, stock: dict[str, int]) -> None:
        self.stock = stock
        self.deducted: list[tuple[str, int]] = []
        self.restocked: list[tuple[str, int]] = []

    def deduct(self, sku: str, quantity: int) -> None:
        available = self.stock.get(sku, 0)
        if quantity > available:
            raise OutOfStockError(sku, requested=quantity, available=available)
        self.stock[sku] = available - quantity
        self.deducted.append((sku, quantity))

    def restock(self, sku: str, quantity: int) -> None:
        self.stock[sku] = self.stock.get(sku, 0) + quantity
        self.restocked.append((sku, quantity))


class FakeNumbers(OrderNumberGenerator):
    def __init__(self, value: str = "ORD-TEST01") -> None:
        self._value = value

    def next(self) -> OrderNumber:
        return OrderNumber(self._value)


class FixedClock(Clock):
    def now(self) -> datetime:
        return datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


class FakeOrders(OrderRepository):
    def __init__(self) -> None:
        self._by_number: dict[tuple[str, str], Order] = {}
        self._sequence = 0

    def add(self, order: Order) -> Order:
        self._sequence += 1
        stored = _with_id(order, self._sequence)
        self._by_number[(order.owner, order.number.value)] = stored
        return stored

    def get_for_owner(self, owner: str, number: str) -> Order:
        try:
            return self._by_number[(owner, number)]
        except KeyError as exc:
            raise OrderNotFoundError(number) from exc

    def get_for_update(self, owner: str, number: str) -> Order:
        return self.get_for_owner(owner, number)

    def list_for_owner(
        self, owner: str, *, limit: int, offset: int
    ) -> tuple[tuple[Order, ...], int]:
        owned = [o for (own, _), o in self._by_number.items() if own == owner]
        owned.sort(key=lambda o: o.id or 0, reverse=True)
        return tuple(owned[offset : offset + limit]), len(owned)

    def set_status(self, order: Order, status: OrderStatus) -> Order:
        updated = _with_status(order, status)
        self._by_number[(order.owner, order.number.value)] = updated
        return updated


class RecordingAudit(AuditRecorder):
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: tuple[FieldChange, ...] = (),
    ) -> None:
        self.records.append(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "actor": actor,
                "changes": changes,
            }
        )


def _with_id(order: Order, new_id: int) -> Order:
    from dataclasses import replace

    return replace(order, id=new_id)


def _with_status(order: Order, status: OrderStatus) -> Order:
    from dataclasses import replace

    return replace(order, status=status)


def _money(amount: str, currency: str = "IRR") -> Money:
    return Money(amount=Decimal(amount), currency=currency)


def _build_place_order(
    *,
    cart_items: tuple[CheckoutLine, ...],
    prices: dict[str, Money],
    stock: dict[str, int],
    currency: str | None = "IRR",
    uow: FakeUnitOfWork | None = None,
    inventory: FakeInventory | None = None,
    orders: FakeOrders | None = None,
    audit: RecordingAudit | None = None,
) -> PlaceOrder:
    return PlaceOrder(
        unit_of_work=uow or FakeUnitOfWork(),
        carts=FakeCart(cart_items),
        pricing=FakePricing(prices),
        channels=FakeChannels(currency),
        inventory=inventory or FakeInventory(stock),
        orders=orders or FakeOrders(),
        numbers=FakeNumbers(),
        clock=FixedClock(),
        audit=audit or RecordingAudit(),
    )


# --- PlaceOrder ----------------------------------------------------------


class TestPlaceOrder:
    def test_captures_prices_and_totals_exactly(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 2), CheckoutLine("DR-250", 1)),
            prices={"HB-250": _money("120000.00"), "DR-250": _money("150000.00")},
            stock={"HB-250": 5, "DR-250": 5},
        )

        order = place.execute(PlaceOrderCommand(owner="7", channel="ir-main"))

        assert order.total.amount == Decimal("390000.00")
        assert order.status is OrderStatus.PENDING
        assert order.currency == "IRR"
        assert order.id is not None

    def test_deducts_stock_for_each_line(self) -> None:
        inventory = FakeInventory({"HB-250": 5})
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 2),),
            prices={"HB-250": _money("120000.00")},
            stock={},
            inventory=inventory,
        )

        place.execute(PlaceOrderCommand(owner="7", channel="ir-main"))

        assert inventory.stock["HB-250"] == 3

    def test_clears_the_cart_on_success(self) -> None:
        cart = FakeCart((CheckoutLine("HB-250", 1),))
        place = PlaceOrder(
            unit_of_work=FakeUnitOfWork(),
            carts=cart,
            pricing=FakePricing({"HB-250": _money("120000.00")}),
            channels=FakeChannels("IRR"),
            inventory=FakeInventory({"HB-250": 5}),
            orders=FakeOrders(),
            numbers=FakeNumbers(),
            clock=FixedClock(),
            audit=RecordingAudit(),
        )

        place.execute(PlaceOrderCommand(owner="7", channel="ir-main"))

        assert cart.cleared is True

    def test_audits_the_placement(self) -> None:
        audit = RecordingAudit()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 2),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            audit=audit,
        )

        place.execute(PlaceOrderCommand(owner="7", channel="ir-main"))

        record = audit.records[-1]
        assert record["action"] == "order.placed"
        assert record["resource_type"] == "order"
        assert record["resource_id"] == "ORD-TEST01"
        assert record["actor"] == "7"

    def test_never_logs_the_amount(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
        )

        with capture_logs() as logs:
            place.execute(PlaceOrderCommand(owner="7", channel="ir-main"))

        assert not any("120000" in str(event) for event in logs)

    def test_an_empty_cart_is_rejected_and_rolls_back(self) -> None:
        uow = FakeUnitOfWork()
        place = _build_place_order(cart_items=(), prices={}, stock={}, uow=uow)

        with pytest.raises(EmptyCartError):
            place.execute(PlaceOrderCommand(owner="7", channel="ir-main"))
        assert uow.rolled_back is True
        assert uow.committed is False

    def test_an_unknown_channel_is_rejected(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            currency=None,
        )

        with pytest.raises(UnknownChannelError):
            place.execute(PlaceOrderCommand(owner="7", channel="ghost"))

    def test_an_unpriced_line_is_rejected(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={},  # variant lost its price since being added
            stock={"HB-250": 5},
        )

        with pytest.raises(VariantNotPurchasableError):
            place.execute(PlaceOrderCommand(owner="7", channel="ir-main"))

    def test_an_oversell_rolls_the_whole_order_back(self) -> None:
        # Two lines: the first deducts, the second oversells. The whole placement must
        # roll back -- no order, and (in the real adapter) the first deduction reverts.
        uow = FakeUnitOfWork()
        inventory = FakeInventory({"HB-250": 5, "DR-250": 0})
        orders = FakeOrders()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1), CheckoutLine("DR-250", 1)),
            prices={"HB-250": _money("120000.00"), "DR-250": _money("150000.00")},
            stock={},
            uow=uow,
            inventory=inventory,
            orders=orders,
        )

        with pytest.raises(OutOfStockError):
            place.execute(PlaceOrderCommand(owner="7", channel="ir-main"))
        assert uow.rolled_back is True
        # No order was persisted.
        assert orders.list_for_owner("7", limit=10, offset=0) == ((), 0)


# --- ListMyOrders / GetMyOrder -------------------------------------------


class TestListMyOrders:
    def _seed(self, orders: FakeOrders, owner: str, count: int) -> None:
        for i in range(count):
            PlaceOrder(
                unit_of_work=FakeUnitOfWork(),
                carts=FakeCart((CheckoutLine("HB-250", 1),)),
                pricing=FakePricing({"HB-250": _money("120000.00")}),
                channels=FakeChannels("IRR"),
                inventory=FakeInventory({"HB-250": 1000}),
                orders=orders,
                numbers=FakeNumbers(f"ORD-N{i:04d}"),
                clock=FixedClock(),
                audit=RecordingAudit(),
            ).execute(PlaceOrderCommand(owner=owner, channel="ir-main"))

    def test_lists_only_the_owners_orders(self) -> None:
        orders = FakeOrders()
        self._seed(orders, "7", 2)
        self._seed(orders, "8", 1)

        page = ListMyOrders(orders).execute(ListMyOrdersQuery(owner="7"))

        assert page.total == 2
        assert all(o.owner == "7" for o in page.items)

    def test_windows_by_limit_and_offset(self) -> None:
        orders = FakeOrders()
        self._seed(orders, "7", 3)

        page = ListMyOrders(orders).execute(ListMyOrdersQuery(owner="7", limit=1, offset=1))

        assert len(page.items) == 1
        assert page.total == 3

    @pytest.mark.parametrize("limit", [0, -1, 101])
    def test_rejects_an_out_of_range_limit(self, limit: int) -> None:
        with pytest.raises(InvalidOrderPageError):
            ListMyOrders(FakeOrders()).execute(ListMyOrdersQuery(owner="7", limit=limit))

    def test_rejects_a_negative_offset(self) -> None:
        with pytest.raises(InvalidOrderPageError):
            ListMyOrders(FakeOrders()).execute(ListMyOrdersQuery(owner="7", offset=-1))


class TestGetMyOrder:
    def test_returns_the_owners_order(self) -> None:
        orders = FakeOrders()
        _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            orders=orders,
        ).execute(PlaceOrderCommand(owner="7", channel="ir-main"))

        order = GetMyOrder(orders).execute(owner="7", number="ORD-TEST01")

        assert order.number.value == "ORD-TEST01"

    def test_another_owner_cannot_read_it(self) -> None:
        orders = FakeOrders()
        _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            orders=orders,
        ).execute(PlaceOrderCommand(owner="7", channel="ir-main"))

        with pytest.raises(OrderNotFoundError):
            GetMyOrder(orders).execute(owner="8", number="ORD-TEST01")

    def test_a_missing_order_raises_not_found(self) -> None:
        with pytest.raises(OrderNotFoundError):
            GetMyOrder(FakeOrders()).execute(owner="7", number="ORD-NOPE99")


# --- CancelMyOrder -------------------------------------------------------


class TestCancelMyOrder:
    def _place(self, orders: FakeOrders, inventory: FakeInventory) -> Order:
        place = PlaceOrder(
            unit_of_work=FakeUnitOfWork(),
            carts=FakeCart((CheckoutLine("HB-250", 2),)),
            pricing=FakePricing({"HB-250": _money("120000.00")}),
            channels=FakeChannels("IRR"),
            inventory=inventory,
            orders=orders,
            numbers=FakeNumbers(),
            clock=FixedClock(),
            audit=RecordingAudit(),
        )
        return place.execute(PlaceOrderCommand(owner="7", channel="ir-main"))

    def test_cancels_a_pending_order_and_restocks(self) -> None:
        orders = FakeOrders()
        inventory = FakeInventory({"HB-250": 5})
        self._place(orders, inventory)  # deducts 2 -> 3 left
        audit = RecordingAudit()

        cancel = CancelMyOrder(
            unit_of_work=FakeUnitOfWork(), orders=orders, inventory=inventory, audit=audit
        )
        result = cancel.execute(CancelMyOrderCommand(owner="7", number="ORD-TEST01"))

        assert result.status is OrderStatus.CANCELLED
        assert inventory.stock["HB-250"] == 5  # restored
        assert audit.records[-1]["action"] == "order.cancelled"

    def test_rolls_back_if_restock_would_fail(self) -> None:
        # A cancel that raises inside the transaction must not commit the status change.
        orders = FakeOrders()
        inventory = FakeInventory({"HB-250": 5})
        self._place(orders, inventory)
        uow = FakeUnitOfWork()

        class ExplodingInventory(FakeInventory):
            def restock(self, sku: str, quantity: int) -> None:
                raise RuntimeError("boom")

        exploding = ExplodingInventory({"HB-250": 3})
        cancel = CancelMyOrder(
            unit_of_work=uow, orders=orders, inventory=exploding, audit=RecordingAudit()
        )

        with pytest.raises(RuntimeError):
            cancel.execute(CancelMyOrderCommand(owner="7", number="ORD-TEST01"))
        assert uow.rolled_back is True

    def test_cannot_cancel_someone_elses_order(self) -> None:
        orders = FakeOrders()
        inventory = FakeInventory({"HB-250": 5})
        self._place(orders, inventory)

        cancel = CancelMyOrder(
            unit_of_work=FakeUnitOfWork(),
            orders=orders,
            inventory=inventory,
            audit=RecordingAudit(),
        )
        with pytest.raises(OrderNotFoundError):
            cancel.execute(CancelMyOrderCommand(owner="8", number="ORD-TEST01"))

    def test_cannot_cancel_a_non_pending_order(self) -> None:
        orders = FakeOrders()
        inventory = FakeInventory({"HB-250": 5})
        order = self._place(orders, inventory)
        orders.set_status(order, OrderStatus.PAID)

        cancel = CancelMyOrder(
            unit_of_work=FakeUnitOfWork(),
            orders=orders,
            inventory=inventory,
            audit=RecordingAudit(),
        )
        with pytest.raises(OrderNotCancellableError):
            cancel.execute(CancelMyOrderCommand(owner="7", number="ORD-TEST01"))
