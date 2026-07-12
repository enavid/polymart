"""Unit tests for the order use cases against fakes (no DB, no framework).

These exercise the orchestration: price capture, atomic stock deduction and rollback,
audit recording, owner-scoping, pagination bounds, and the cancel/restock flow. The
fakes stand in for the Django adapters wired at the composition root.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.order.ports import (
    AddressReader,
    CartForCheckout,
    ChannelReader,
    CheckoutLine,
    Clock,
    InlineShippingAddress,
    Inventory,
    OrderNumberGenerator,
    OrderRepository,
    OwnedAddress,
    PricingReader,
    ShippingQuote,
    ShippingRateReader,
    TaxCalculator,
    TaxQuote,
    UnitOfWork,
    VariantWeightReader,
)
from src.application.order.use_cases import (
    CancelMyOrder,
    CancelMyOrderCommand,
    CreateManualOrder,
    CreateManualOrderCommand,
    GetMyOrder,
    GetOrderForInvoice,
    InvalidOrderPageError,
    ListMyOrders,
    ListMyOrdersQuery,
    ManualOrderItem,
    PlaceOrder,
    PlaceOrderCommand,
)
from src.application.shared.events import EventPublisher
from src.application.shared.owner import safe_owner
from src.domain.audit.entities import FieldChange
from src.domain.order.entities import Order
from src.domain.order.events import OrderPlaced
from src.domain.order.exceptions import (
    DuplicateOrderLineError,
    EmptyCartError,
    EmptyOrderError,
    OrderNotCancellableError,
    OrderNotFoundError,
    OutOfStockError,
    UnknownChannelError,
    UnknownShippingAddressError,
    UnknownShippingMethodError,
    VariantNotPurchasableError,
)
from src.domain.order.value_objects import Money, OrderNumber, OrderStatus
from src.domain.shared.events import DomainEvent

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


class FakeWeights(VariantWeightReader):
    """Per-sku weight in grams; unset skus weigh 0 (the unweighed default)."""

    def __init__(self, weights: dict[str, int] | None = None) -> None:
        self._weights = weights or {}

    def weight_of(self, skus: Sequence[str]) -> dict[str, int]:
        return {sku: self._weights[sku] for sku in skus if sku in self._weights}


class FakeChannels(ChannelReader):
    def __init__(self, currency: str | None) -> None:
        self._currency = currency

    def currency_of(self, channel: str) -> str | None:
        return self._currency


class FakeShipping(ShippingRateReader):
    """Quotes a small set of known methods; unknown codes quote ``None`` (unavailable).

    Defaults to a *zero-cost* ``standard`` method so checkout tests that are not about
    shipping keep their goods-only totals; pass ``costs`` to exercise a real shipping charge.
    """

    def __init__(self, costs: dict[str, Money] | None = None) -> None:
        self._costs = costs if costs is not None else {"standard": Money(Decimal("0"), "IRR")}
        self.seen_province: str | None = None
        self.seen_city: str | None = None
        self.seen_weight: int | None = None

    def quote(
        self,
        *,
        channel: str,
        method_code: str,
        currency: str,
        province: str,
        city: str,
        weight_grams: int = 0,
    ) -> ShippingQuote | None:
        self.seen_province = province
        self.seen_city = city
        self.seen_weight = weight_grams
        cost = self._costs.get(method_code)
        if cost is None or cost.currency != currency:
            return None
        return ShippingQuote(method_code=method_code, method_name=method_code.title(), cost=cost)


class FakeTax(TaxCalculator):
    """Computes tax at a fixed percentage of the taxable base.

    Defaults to *no tax* (``rate=None``) so checkout tests that are not about tax keep their
    goods+shipping totals; pass a rate to exercise a real tax charge. The amount mirrors the
    domain service (exact ``Decimal``, half-up to 4 dp) so a use-case test asserts against the
    same rounded value the real bridge produces.
    """

    def __init__(self, rate: Decimal | None = None) -> None:
        self._rate = rate
        self.seen_taxable: Money | None = None

    def calculate(self, *, channel: str, taxable: Money) -> TaxQuote | None:
        self.seen_taxable = taxable
        if self._rate is None:
            return None
        amount = (taxable.amount * self._rate / Decimal("100")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        return TaxQuote(rate=self._rate, amount=Money(amount, taxable.currency))


_DEFAULT_OWNED_ADDRESS = OwnedAddress(
    recipient_name="Sara Ahmadi",
    phone_number="+989123456789",
    province="Tehran",
    city="Tehran",
    postal_code="1234567890",
    line1="Valiasr St, No. 1",
    line2=None,
)


_DEFAULT_ADDRESS_ID = "ADDR-TEST01"


class FakeAddresses(AddressReader):
    """Defaults to letting *any* owner resolve the default address id, so tests that
    are not specifically about address ownership (pagination across owners, etc.)
    don't need to wire it up explicitly. Pass an explicit mapping to test ownership.
    """

    def __init__(self, addresses: dict[tuple[str, str], OwnedAddress] | None = None) -> None:
        self._addresses = addresses

    def get_for_owner(self, owner: str, address_id: str) -> OwnedAddress | None:
        if self._addresses is not None:
            return self._addresses.get((owner, address_id))
        return _DEFAULT_OWNED_ADDRESS if address_id == _DEFAULT_ADDRESS_ID else None


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

    def get(self, number: str) -> Order:
        for (_owner, num), order in self._by_number.items():
            if num == number:
                return order
        raise OrderNotFoundError(number)

    def get_for_owner(self, owner: str, number: str) -> Order:
        try:
            return self._by_number[(owner, number)]
        except KeyError as exc:
            raise OrderNotFoundError(number) from exc

    def get_for_update(self, owner: str, number: str) -> Order:
        return self.get_for_owner(owner, number)

    def get_for_update_any(self, number: str) -> Order:
        return self.get(number)

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


class RecordingEventPublisher(EventPublisher):
    """Records the domain events a use case publishes, in order.

    Publishes immediately (the use case calls ``publish`` inside its transaction, and this
    fake has no notion of commit) -- enough to assert *what* was published. The real
    after-commit / discard-on-rollback timing is covered by the integration test.
    """

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


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
    addresses: FakeAddresses | None = None,
    shipping: FakeShipping | None = None,
    tax: FakeTax | None = None,
    weights: FakeWeights | None = None,
    audit: RecordingAudit | None = None,
    events: RecordingEventPublisher | None = None,
) -> PlaceOrder:
    return PlaceOrder(
        unit_of_work=uow or FakeUnitOfWork(),
        carts=FakeCart(cart_items),
        pricing=FakePricing(prices),
        weights=weights or FakeWeights(),
        channels=FakeChannels(currency),
        addresses=addresses or FakeAddresses(),
        shipping=shipping or FakeShipping(),
        tax=tax or FakeTax(),
        inventory=inventory or FakeInventory(stock),
        orders=orders or FakeOrders(),
        numbers=FakeNumbers(),
        clock=FixedClock(),
        audit=audit or RecordingAudit(),
        events=events or RecordingEventPublisher(),
    )


# --- PlaceOrder ----------------------------------------------------------


class TestPlaceOrder:
    def test_captures_prices_and_totals_exactly(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 2), CheckoutLine("DR-250", 1)),
            prices={"HB-250": _money("120000.00"), "DR-250": _money("150000.00")},
            stock={"HB-250": 5, "DR-250": 5},
        )

        order = place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        assert order.total.amount == Decimal("390000.00")
        assert order.status is OrderStatus.PENDING
        assert order.currency == "IRR"
        assert order.id is not None

    def test_captures_the_shipping_address_from_the_address_book(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
        )

        order = place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        assert order.shipping_address.recipient_name == "Sara Ahmadi"
        assert order.shipping_address.city == "Tehran"

    def test_an_unknown_address_is_rejected_and_rolls_back(self) -> None:
        uow = FakeUnitOfWork()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            uow=uow,
        )

        with pytest.raises(UnknownShippingAddressError):
            place.execute(
                PlaceOrderCommand(
                    owner="7",
                    channel="ir-main",
                    shipping_method="standard",
                    address_id="ADDR-NOPE99",
                )
            )
        # Never entered the transaction at all (resolved before the unit of work).
        assert uow.committed is False
        assert uow.rolled_back is False

    def test_cannot_checkout_with_another_owners_address(self) -> None:
        # Owned only by "8"; "7" checking out with it must be refused, exactly like an
        # unknown channel -- never silently ship to someone else's saved address.
        addresses = FakeAddresses({("8", "ADDR-OTHER0"): _DEFAULT_OWNED_ADDRESS})
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            addresses=addresses,
        )

        with pytest.raises(UnknownShippingAddressError):
            place.execute(
                PlaceOrderCommand(
                    owner="7",
                    channel="ir-main",
                    shipping_method="standard",
                    address_id="ADDR-OTHER0",
                )
            )

    def test_deducts_stock_for_each_line(self) -> None:
        inventory = FakeInventory({"HB-250": 5})
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 2),),
            prices={"HB-250": _money("120000.00")},
            stock={},
            inventory=inventory,
        )

        place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        assert inventory.stock["HB-250"] == 3

    def test_clears_the_cart_on_success(self) -> None:
        cart = FakeCart((CheckoutLine("HB-250", 1),))
        place = PlaceOrder(
            unit_of_work=FakeUnitOfWork(),
            carts=cart,
            pricing=FakePricing({"HB-250": _money("120000.00")}),
            weights=FakeWeights(),
            channels=FakeChannels("IRR"),
            addresses=FakeAddresses(),
            shipping=FakeShipping(),
            tax=FakeTax(),
            inventory=FakeInventory({"HB-250": 5}),
            orders=FakeOrders(),
            numbers=FakeNumbers(),
            clock=FixedClock(),
            audit=RecordingAudit(),
            events=RecordingEventPublisher(),
        )

        place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        assert cart.cleared is True

    def test_audits_the_placement(self) -> None:
        audit = RecordingAudit()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 2),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            audit=audit,
        )

        place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        record = audit.records[-1]
        assert record["action"] == "order.placed"
        assert record["resource_type"] == "order"
        assert record["resource_id"] == "ORD-TEST01"
        assert record["actor"] == "7"

    def test_publishes_order_placed_with_the_captured_total(self) -> None:
        events = RecordingEventPublisher()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 2),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            events=events,
        )

        place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        [event] = events.events
        assert isinstance(event, OrderPlaced)
        assert event.order_number == "ORD-TEST01"
        assert event.owner == "7"
        assert event.channel == "ir-main"
        assert event.currency == "IRR"
        assert event.total == Decimal("240000.00")
        assert event.line_count == 1

    def test_publishes_no_event_when_the_placement_rolls_back(self) -> None:
        # An oversell fails before the publish line, so no OrderPlaced is announced -- the
        # unit-level counterpart of the adapter discarding an after-commit delivery.
        events = RecordingEventPublisher()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 5),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 1},
            events=events,
        )

        with pytest.raises(OutOfStockError):
            place.execute(
                PlaceOrderCommand(
                    owner="7",
                    channel="ir-main",
                    shipping_method="standard",
                    address_id="ADDR-TEST01",
                )
            )
        assert events.events == []

    def test_never_logs_the_amount(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
        )

        with capture_logs() as logs:
            place.execute(
                PlaceOrderCommand(
                    owner="7",
                    channel="ir-main",
                    shipping_method="standard",
                    address_id="ADDR-TEST01",
                )
            )

        assert not any("120000" in str(event) for event in logs)

    def test_an_empty_cart_is_rejected_and_rolls_back(self) -> None:
        uow = FakeUnitOfWork()
        place = _build_place_order(cart_items=(), prices={}, stock={}, uow=uow)

        with pytest.raises(EmptyCartError):
            place.execute(
                PlaceOrderCommand(
                    owner="7",
                    channel="ir-main",
                    shipping_method="standard",
                    address_id="ADDR-TEST01",
                )
            )
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
            place.execute(
                PlaceOrderCommand(
                    owner="7", channel="ghost", shipping_method="standard", address_id="ADDR-TEST01"
                )
            )

    def test_an_unpriced_line_is_rejected(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={},  # variant lost its price since being added
            stock={"HB-250": 5},
        )

        with pytest.raises(VariantNotPurchasableError):
            place.execute(
                PlaceOrderCommand(
                    owner="7",
                    channel="ir-main",
                    shipping_method="standard",
                    address_id="ADDR-TEST01",
                )
            )

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
            place.execute(
                PlaceOrderCommand(
                    owner="7",
                    channel="ir-main",
                    shipping_method="standard",
                    address_id="ADDR-TEST01",
                )
            )
        assert uow.rolled_back is True
        # No order was persisted.
        assert orders.list_for_owner("7", limit=10, offset=0) == ((), 0)


class TestPlaceOrderShipping:
    def test_captures_the_selected_shipping_cost_into_the_total(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 2),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            shipping=FakeShipping({"express": _money("120000.00")}),
        )

        order = place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="express", address_id="ADDR-TEST01"
            )
        )

        assert order.items_subtotal.amount == Decimal("240000.00")
        assert order.shipping is not None
        assert order.shipping.method_code == "express"
        assert order.shipping.cost.amount == Decimal("120000.00")
        assert order.total.amount == Decimal("360000.00")  # goods + shipping

    def test_publishes_the_grand_total_including_shipping(self) -> None:
        events = RecordingEventPublisher()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            shipping=FakeShipping({"express": _money("30000.00")}),
            events=events,
        )

        place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="express", address_id="ADDR-TEST01"
            )
        )

        [event] = events.events
        assert event.total == Decimal("150000.00")  # 120000 goods + 30000 shipping

    def test_audits_the_shipping_selection(self) -> None:
        audit = RecordingAudit()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            shipping=FakeShipping({"express": _money("30000.00")}),
            audit=audit,
        )

        place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="express", address_id="ADDR-TEST01"
            )
        )

        changes = {c.field: c.after for c in audit.records[-1]["changes"]}  # type: ignore[attr-defined]
        assert changes["shipping_method"] == "express"
        assert changes["shipping_cost"] == "30000.00"

    def test_quotes_the_method_against_the_captured_destination(self) -> None:
        # The rate must be resolved from the order's shipping address (province/city), so a
        # zoned rate re-resolves server-side rather than trusting whatever the client saw.
        shipping = FakeShipping({"standard": _money("50000.00")})
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            shipping=shipping,
        )

        place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        assert shipping.seen_province == "Tehran"
        assert shipping.seen_city == "Tehran"

    def test_an_unknown_shipping_method_rolls_back_and_places_nothing(self) -> None:
        # The method is quoted inside the unit of work (a weight-priced method needs the cart's
        # total weight), so an unknown method rolls the transaction back rather than being
        # refused before it. It is the first step, before any reservation, so nothing is
        # committed and no stock moves -- the same observable outcome.
        uow = FakeUnitOfWork()
        inventory = FakeInventory({"HB-250": 5})
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            shipping=FakeShipping({"standard": _money("50000.00")}),
            inventory=inventory,
            uow=uow,
        )

        with pytest.raises(UnknownShippingMethodError):
            place.execute(
                PlaceOrderCommand(
                    owner="7", channel="ir-main", shipping_method="drone", address_id="ADDR-TEST01"
                )
            )
        assert uow.committed is False
        assert inventory.deducted == []  # nothing reserved before the method was rejected


class TestPlaceOrderTax:
    def test_captures_tax_on_the_subtotal_plus_shipping(self) -> None:
        tax = FakeTax(Decimal("9"))
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            shipping=FakeShipping({"standard": _money("50000.00")}),
            tax=tax,
        )

        order = place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        # Tax base is goods 120000 + shipping 50000 = 170000; 9% = 15300.
        assert tax.seen_taxable is not None
        assert tax.seen_taxable.amount == Decimal("170000.00")
        assert order.tax is not None
        assert order.tax.rate == Decimal("9")
        assert order.tax.amount.amount == Decimal("15300.00")
        # Grand total = goods + shipping + tax.
        assert order.total.amount == Decimal("185300.00")

    def test_no_tax_leaves_the_total_at_goods_plus_shipping(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            shipping=FakeShipping({"standard": _money("50000.00")}),
            tax=FakeTax(None),  # untaxed channel
        )

        order = place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        assert order.tax is None
        assert order.total.amount == Decimal("170000.00")

    def test_audits_the_tax_amount(self) -> None:
        audit = RecordingAudit()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            shipping=FakeShipping({"standard": _money("50000.00")}),
            tax=FakeTax(Decimal("9")),
            audit=audit,
        )

        place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        changes = {c.field: c.after for c in audit.records[-1]["changes"]}  # type: ignore[attr-defined]
        # The tax service quantizes to the stored precision (4 dp), so the amount is exact.
        assert changes["tax"] == "15300.0000"

    def test_publishes_the_grand_total_including_tax(self) -> None:
        events = RecordingEventPublisher()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            shipping=FakeShipping({"standard": _money("50000.00")}),
            tax=FakeTax(Decimal("9")),
            events=events,
        )

        place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        [event] = events.events
        assert event.total == Decimal("185300.00")


_INLINE_ADDRESS = InlineShippingAddress(
    recipient_name="Guest Buyer",
    phone_number="09121112233",
    province="Isfahan",
    city="Isfahan",
    postal_code="8134567890",
    line1="Chaharbagh St, No. 9",
    line2=None,
)


class TestPlaceOrderInlineShipping:
    """A guest (owner ``g:<token>``) checks out with a one-off inline shipping address,
    never touching the address book (which they have none of)."""

    def test_captures_the_inline_shipping_address(self) -> None:
        addresses = FakeAddresses({})  # no saved addresses for anyone
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            addresses=addresses,
        )

        order = place.execute(
            PlaceOrderCommand(
                owner="g:tok-abc",
                channel="ir-main",
                shipping_method="standard",
                shipping_address=_INLINE_ADDRESS,
            )
        )

        assert order.owner == "g:tok-abc"
        assert order.shipping_address.recipient_name == "Guest Buyer"
        assert order.shipping_address.city == "Isfahan"
        assert order.shipping_address.postal_code == "8134567890"

    def test_inline_capture_never_reads_the_address_book(self) -> None:
        # If the address reader is consulted at all for an inline checkout it is a bug;
        # a reader that explodes on use proves the inline path bypasses it entirely.
        class ExplodingAddresses(AddressReader):
            def get_for_owner(self, owner: str, address_id: str) -> OwnedAddress | None:
                raise AssertionError("inline checkout must not read the address book")

        place = PlaceOrder(
            unit_of_work=FakeUnitOfWork(),
            carts=FakeCart((CheckoutLine("HB-250", 1),)),
            pricing=FakePricing({"HB-250": _money("120000.00")}),
            weights=FakeWeights(),
            channels=FakeChannels("IRR"),
            addresses=ExplodingAddresses(),
            shipping=FakeShipping(),
            tax=FakeTax(),
            inventory=FakeInventory({"HB-250": 5}),
            orders=FakeOrders(),
            numbers=FakeNumbers(),
            clock=FixedClock(),
            audit=RecordingAudit(),
            events=RecordingEventPublisher(),
        )

        order = place.execute(
            PlaceOrderCommand(
                owner="g:tok-abc",
                channel="ir-main",
                shipping_method="standard",
                shipping_address=_INLINE_ADDRESS,
            )
        )
        assert order.total.amount == Decimal("120000.00")

    def test_audits_the_guest_placement_by_a_redacted_owner_fingerprint(self) -> None:
        # The guest token is a bearer session credential; it must never reach the durable
        # audit trail. The actor is the non-reversible fingerprint (see safe_owner), so a
        # guest stays correlatable without the raw token being persisted.
        audit = RecordingAudit()
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            audit=audit,
        )

        place.execute(
            PlaceOrderCommand(
                owner="g:tok-xyz",
                channel="ir-main",
                shipping_method="standard",
                shipping_address=_INLINE_ADDRESS,
            )
        )

        actor = audit.records[-1]["actor"]
        assert actor == safe_owner("g:tok-xyz")
        assert "tok-xyz" not in actor

    def test_never_logs_the_raw_guest_token(self) -> None:
        # A guest's session token is a credential -- it must not appear in any structured
        # log event emitted while placing their order.
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
        )

        with capture_logs() as logs:
            place.execute(
                PlaceOrderCommand(
                    owner="g:tok-secret",
                    channel="ir-main",
                    shipping_method="standard",
                    shipping_address=_INLINE_ADDRESS,
                )
            )

        assert not any("tok-secret" in str(event) for event in logs)

    def test_requires_either_an_address_id_or_an_inline_address(self) -> None:
        place = _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
        )

        with pytest.raises(UnknownShippingAddressError):
            place.execute(
                PlaceOrderCommand(owner="g:tok-abc", channel="ir-main", shipping_method="standard")
            )


# --- ListMyOrders / GetMyOrder -------------------------------------------


class TestListMyOrders:
    def _seed(self, orders: FakeOrders, owner: str, count: int) -> None:
        for i in range(count):
            PlaceOrder(
                unit_of_work=FakeUnitOfWork(),
                carts=FakeCart((CheckoutLine("HB-250", 1),)),
                pricing=FakePricing({"HB-250": _money("120000.00")}),
                weights=FakeWeights(),
                channels=FakeChannels("IRR"),
                addresses=FakeAddresses(),
                shipping=FakeShipping(),
                tax=FakeTax(),
                inventory=FakeInventory({"HB-250": 1000}),
                orders=orders,
                numbers=FakeNumbers(f"ORD-N{i:04d}"),
                clock=FixedClock(),
                audit=RecordingAudit(),
                events=RecordingEventPublisher(),
            ).execute(
                PlaceOrderCommand(
                    owner=owner,
                    channel="ir-main",
                    shipping_method="standard",
                    address_id="ADDR-TEST01",
                )
            )

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
        ).execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

        order = GetMyOrder(orders).execute(owner="7", number="ORD-TEST01")

        assert order.number.value == "ORD-TEST01"

    def test_another_owner_cannot_read_it(self) -> None:
        orders = FakeOrders()
        _build_place_order(
            cart_items=(CheckoutLine("HB-250", 1),),
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            orders=orders,
        ).execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

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
            weights=FakeWeights(),
            channels=FakeChannels("IRR"),
            addresses=FakeAddresses(),
            shipping=FakeShipping(),
            tax=FakeTax(),
            inventory=inventory,
            orders=orders,
            numbers=FakeNumbers(),
            clock=FixedClock(),
            audit=RecordingAudit(),
            events=RecordingEventPublisher(),
        )
        return place.execute(
            PlaceOrderCommand(
                owner="7", channel="ir-main", shipping_method="standard", address_id="ADDR-TEST01"
            )
        )

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


# --- CreateManualOrder ---------------------------------------------------


def _build_create_manual_order(
    *,
    prices: dict[str, Money],
    stock: dict[str, int],
    currency: str | None = "IRR",
    uow: FakeUnitOfWork | None = None,
    inventory: FakeInventory | None = None,
    orders: FakeOrders | None = None,
    tax: FakeTax | None = None,
    audit: RecordingAudit | None = None,
    events: RecordingEventPublisher | None = None,
) -> CreateManualOrder:
    return CreateManualOrder(
        unit_of_work=uow or FakeUnitOfWork(),
        pricing=FakePricing(prices),
        channels=FakeChannels(currency),
        tax=tax or FakeTax(),
        inventory=inventory or FakeInventory(stock),
        orders=orders or FakeOrders(),
        numbers=FakeNumbers(),
        clock=FixedClock(),
        audit=audit or RecordingAudit(),
        events=events or RecordingEventPublisher(),
    )


class TestCreateManualOrder:
    def test_captures_prices_owner_and_shipping(self) -> None:
        create = _build_create_manual_order(
            prices={"HB-250": _money("120000.00"), "DR-250": _money("150000.00")},
            stock={"HB-250": 5, "DR-250": 5},
        )

        order = create.execute(
            CreateManualOrderCommand(
                actor="u:9",
                channel="ir-main",
                items=(ManualOrderItem("HB-250", 2), ManualOrderItem("DR-250", 1)),
                shipping_address=_INLINE_ADDRESS,
            )
        )

        assert order.owner == "u:9"
        assert order.status is OrderStatus.PENDING
        assert order.total == _money("390000.00")
        assert order.shipping_address.recipient_name == "Guest Buyer"
        assert [line.sku.value for line in order.lines] == ["HB-250", "DR-250"]

    def test_captures_tax_on_the_goods_subtotal(self) -> None:
        tax = FakeTax(Decimal("9"))
        create = _build_create_manual_order(
            prices={"HB-250": _money("120000.00")},
            stock={"HB-250": 5},
            tax=tax,
        )

        order = create.execute(
            CreateManualOrderCommand(
                actor="u:9",
                channel="ir-main",
                items=(ManualOrderItem("HB-250", 1),),
                shipping_address=_INLINE_ADDRESS,
            )
        )

        # A manual order has no shipping, so the tax base is the goods subtotal alone.
        assert tax.seen_taxable is not None
        assert tax.seen_taxable.amount == Decimal("120000.00")
        assert order.tax is not None
        assert order.tax.amount.amount == Decimal("10800.00")
        assert order.total.amount == Decimal("130800.00")

    def test_deducts_stock_for_each_line(self) -> None:
        inventory = FakeInventory({"HB-250": 5})
        create = _build_create_manual_order(
            prices={"HB-250": _money("120000.00")}, stock={}, inventory=inventory
        )

        create.execute(
            CreateManualOrderCommand(
                actor="u:9",
                channel="ir-main",
                items=(ManualOrderItem("HB-250", 3),),
                shipping_address=_INLINE_ADDRESS,
            )
        )

        assert inventory.stock["HB-250"] == 2
        assert inventory.deducted == [("HB-250", 3)]

    def test_audits_the_manual_creation_with_origin(self) -> None:
        audit = RecordingAudit()
        create = _build_create_manual_order(
            prices={"HB-250": _money("120000.00")}, stock={"HB-250": 5}, audit=audit
        )

        create.execute(
            CreateManualOrderCommand(
                actor="u:9",
                channel="ir-main",
                items=(ManualOrderItem("HB-250", 1),),
                shipping_address=_INLINE_ADDRESS,
            )
        )

        entry = audit.records[0]
        assert entry["action"] == "order.created_manually"
        assert entry["actor"] == "u:9"
        origins = [c.after for c in entry["changes"] if c.field == "origin"]  # type: ignore[attr-defined]
        assert origins == ["manual"]

    def test_publishes_order_placed_for_the_manual_order(self) -> None:
        # A manual order is a real placed order, so it announces the same OrderPlaced.
        events = RecordingEventPublisher()
        create = _build_create_manual_order(
            prices={"HB-250": _money("120000.00")}, stock={"HB-250": 5}, events=events
        )

        create.execute(
            CreateManualOrderCommand(
                actor="u:9",
                channel="ir-main",
                items=(ManualOrderItem("HB-250", 2),),
                shipping_address=_INLINE_ADDRESS,
            )
        )

        [event] = events.events
        assert isinstance(event, OrderPlaced)
        assert event.owner == "u:9"
        assert event.total == _money("240000.00").amount
        assert event.line_count == 1

    def test_an_oversell_rolls_the_whole_order_back(self) -> None:
        uow = FakeUnitOfWork()
        orders = FakeOrders()
        inventory = FakeInventory({"HB-250": 5, "DR-250": 0})
        create = _build_create_manual_order(
            prices={"HB-250": _money("120000.00"), "DR-250": _money("150000.00")},
            stock={},
            uow=uow,
            inventory=inventory,
            orders=orders,
        )

        with pytest.raises(OutOfStockError):
            create.execute(
                CreateManualOrderCommand(
                    actor="u:9",
                    channel="ir-main",
                    items=(ManualOrderItem("HB-250", 1), ManualOrderItem("DR-250", 1)),
                    shipping_address=_INLINE_ADDRESS,
                )
            )

        assert uow.rolled_back is True
        assert orders.list_for_owner("u:9", limit=10, offset=0) == ((), 0)

    def test_a_duplicate_sku_is_rejected(self) -> None:
        create = _build_create_manual_order(
            prices={"HB-250": _money("120000.00")}, stock={"HB-250": 5}
        )

        with pytest.raises(DuplicateOrderLineError):
            create.execute(
                CreateManualOrderCommand(
                    actor="u:9",
                    channel="ir-main",
                    items=(ManualOrderItem("HB-250", 1), ManualOrderItem("HB-250", 2)),
                    shipping_address=_INLINE_ADDRESS,
                )
            )

    def test_no_items_is_rejected_as_an_empty_order(self) -> None:
        create = _build_create_manual_order(prices={}, stock={})

        with pytest.raises(EmptyOrderError):
            create.execute(
                CreateManualOrderCommand(
                    actor="u:9", channel="ir-main", items=(), shipping_address=_INLINE_ADDRESS
                )
            )

    def test_an_unknown_channel_is_rejected(self) -> None:
        create = _build_create_manual_order(
            prices={"HB-250": _money("120000.00")}, stock={"HB-250": 5}, currency=None
        )

        with pytest.raises(UnknownChannelError):
            create.execute(
                CreateManualOrderCommand(
                    actor="u:9",
                    channel="nope",
                    items=(ManualOrderItem("HB-250", 1),),
                    shipping_address=_INLINE_ADDRESS,
                )
            )

    def test_an_unpriced_line_is_rejected(self) -> None:
        create = _build_create_manual_order(prices={}, stock={"HB-250": 5})

        with pytest.raises(VariantNotPurchasableError):
            create.execute(
                CreateManualOrderCommand(
                    actor="u:9",
                    channel="ir-main",
                    items=(ManualOrderItem("HB-250", 1),),
                    shipping_address=_INLINE_ADDRESS,
                )
            )

    def test_never_logs_the_amount(self) -> None:
        create = _build_create_manual_order(
            prices={"HB-250": _money("120000.00")}, stock={"HB-250": 5}
        )

        with capture_logs() as logs:
            create.execute(
                CreateManualOrderCommand(
                    actor="u:9",
                    channel="ir-main",
                    items=(ManualOrderItem("HB-250", 1),),
                    shipping_address=_INLINE_ADDRESS,
                )
            )

        assert all("120000" not in str(value) for log in logs for value in log.values())


# --- GetOrderForInvoice --------------------------------------------------


class TestGetOrderForInvoice:
    def _seed_order(self, orders: FakeOrders, *, owner: str, number: str) -> None:
        create = _build_create_manual_order(
            prices={"HB-250": _money("120000.00")}, stock={"HB-250": 5}, orders=orders
        )
        # Reuse the number generator's fixed value by monkeying the actor/number path:
        create.execute(
            CreateManualOrderCommand(
                actor=owner,
                channel="ir-main",
                items=(ManualOrderItem("HB-250", 1),),
                shipping_address=_INLINE_ADDRESS,
            )
        )

    def test_reads_any_order_by_number_regardless_of_owner(self) -> None:
        orders = FakeOrders()
        self._seed_order(orders, owner="u:5", number="ORD-TEST01")

        # A staff member (not the owner u:5) issues the pre-invoice; not owner-scoped.
        order = GetOrderForInvoice(orders).execute(number="ORD-TEST01")

        assert order.number.value == "ORD-TEST01"
        assert order.owner == "u:5"

    def test_an_unknown_number_is_not_found(self) -> None:
        with pytest.raises(OrderNotFoundError):
            GetOrderForInvoice(FakeOrders()).execute(number="ORD-NOPE99")

    def test_a_malformed_number_is_rejected(self) -> None:
        from src.domain.order.exceptions import InvalidOrderNumberError

        with pytest.raises(InvalidOrderNumberError):
            GetOrderForInvoice(FakeOrders()).execute(number="not a number")
