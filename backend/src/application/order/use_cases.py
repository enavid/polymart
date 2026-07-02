"""Order use cases (interactors).

Each use case orchestrates the domain to fulfil one application intent: pure
orchestration, dependencies via constructor injection, business rules in the domain,
side effects (logging, audit) observable.

Placing and cancelling an order both move money-relevant state (inventory) and so run
inside a single ``UnitOfWork.atomic()`` and write to the durable audit trail. The
structured logs deliberately never carry the amount (a money value) or any PII: the
actor is the stable user id, and the captured totals live only on the audit entry.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.application.audit.ports import AuditRecorder
from src.application.order.ports import (
    CartForCheckout,
    ChannelReader,
    CheckoutLine,
    Clock,
    Inventory,
    OrderNumberGenerator,
    OrderPage,
    OrderRepository,
    PricingReader,
    UnitOfWork,
)
from src.domain.audit.entities import FieldChange
from src.domain.order.entities import Order
from src.domain.order.exceptions import (
    EmptyCartError,
    OrderNotCancellableError,
    UnknownChannelError,
    VariantNotPurchasableError,
)
from src.domain.order.services import PricedItem, build_order_lines, order_total
from src.domain.order.value_objects import ChannelRef, OrderNumber, OrderQuantity, OrderStatus, Sku

logger = structlog.get_logger(__name__)

# Pagination bounds for a shopper's order history, mirroring the catalog/access read
# windows so a caller cannot ask for an unbounded page.
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100

_RESOURCE_ORDER = "order"
_ACTION_ORDER_PLACED = "order.placed"
_ACTION_ORDER_CANCELLED = "order.cancelled"


class InvalidOrderPageError(Exception):
    """Raised when the requested order-history page window is out of range."""


def _resolve_currency(channels: ChannelReader, channel: str) -> str:
    currency = channels.currency_of(channel)
    if currency is None:
        raise UnknownChannelError(channel)
    return currency


@dataclass(frozen=True)
class PlaceOrderCommand:
    """Input for turning a shopper's cart into a placed order."""

    owner: str
    channel: str


class PlaceOrder:
    """Convert the owner's cart in a channel into a placed order, atomically.

    Prices are *captured* from the current catalog price (a snapshot), stock is
    deducted (refusing an oversell), the order is persisted, the cart is cleared, and
    the placement is audited -- all inside one transaction, so any failure leaves stock,
    cart, and trail exactly as they were.
    """

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        carts: CartForCheckout,
        pricing: PricingReader,
        channels: ChannelReader,
        inventory: Inventory,
        orders: OrderRepository,
        numbers: OrderNumberGenerator,
        clock: Clock,
        audit: AuditRecorder,
    ) -> None:
        self._uow = unit_of_work
        self._carts = carts
        self._pricing = pricing
        self._channels = channels
        self._inventory = inventory
        self._orders = orders
        self._numbers = numbers
        self._clock = clock
        self._audit = audit

    def execute(self, command: PlaceOrderCommand) -> Order:
        channel = ChannelRef(command.channel)
        currency = _resolve_currency(self._channels, channel.value)

        with self._uow.atomic():
            items = self._carts.line_items(command.owner, channel.value)
            if not items:
                raise EmptyCartError(channel.value)

            priced_items = self._capture_and_deduct(items, channel.value, currency)
            lines = build_order_lines(priced_items)
            total = order_total(lines, currency)
            order = Order(
                number=self._numbers.next(),
                owner=command.owner,
                channel=channel,
                currency=currency,
                lines=lines,
                total=total,
                status=OrderStatus.PENDING,
                placed_at=self._clock.now(),
            )
            saved = self._orders.add(order)
            self._carts.clear(command.owner, channel.value)
            self._audit.record(
                action=_ACTION_ORDER_PLACED,
                resource_type=_RESOURCE_ORDER,
                resource_id=saved.number.value,
                actor=command.owner,
                changes=(
                    FieldChange(field="status", after=OrderStatus.PENDING.value),
                    FieldChange(field="total", after=str(total.amount)),
                    FieldChange(field="line_count", after=len(lines)),
                ),
            )

        # Logged outside the money detail: number and shape, never the amount.
        logger.info(
            "order_placed",
            owner=command.owner,
            channel=channel.value,
            order_number=saved.number.value,
            line_count=len(lines),
            currency=currency,
        )
        return saved

    def _capture_and_deduct(
        self, items: tuple[CheckoutLine, ...], channel: str, currency: str
    ) -> list[PricedItem]:
        """Capture each line's current price and deduct its stock (under the txn).

        A line whose variant lost its price since being added is refused (it could not
        be sold); ``inventory.deduct`` refuses an oversell. Because we are inside the
        unit of work, a failure on any line rolls back the deductions already made.
        """
        priced: list[PricedItem] = []
        for item in items:
            sku = Sku(item.sku)
            quantity = OrderQuantity(item.quantity)
            unit_price = self._pricing.price_of(sku.value, channel)
            if unit_price is None:
                raise VariantNotPurchasableError(sku.value, channel)
            if unit_price.currency != currency:  # pragma: no cover - defensive
                raise VariantNotPurchasableError(sku.value, channel)
            self._inventory.deduct(sku.value, quantity.value)
            priced.append(PricedItem(sku=sku, quantity=quantity, unit_price=unit_price))
        return priced


@dataclass(frozen=True)
class ListMyOrdersQuery:
    """Input for reading a shopper's own order history (paged, newest first)."""

    owner: str
    limit: int = DEFAULT_PAGE_LIMIT
    offset: int = 0


class ListMyOrders:
    """List the authenticated shopper's own orders (never another's)."""

    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    def execute(self, query: ListMyOrdersQuery) -> OrderPage:
        limit, offset = self._validated_window(query.limit, query.offset)
        items, total = self._orders.list_for_owner(query.owner, limit=limit, offset=offset)
        logger.debug("orders_listed", owner=query.owner, count=total, returned=len(items))
        return OrderPage(items=tuple(items), total=total)

    @staticmethod
    def _validated_window(limit: int, offset: int) -> tuple[int, int]:
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise InvalidOrderPageError(f"limit must be between 1 and {MAX_PAGE_LIMIT}: {limit}")
        if offset < 0:
            raise InvalidOrderPageError(f"offset must not be negative: {offset}")
        return limit, offset


class GetMyOrder:
    """Read one of the authenticated shopper's own orders by number."""

    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    def execute(self, *, owner: str, number: str) -> Order:
        # Validate the shape first; a malformed number can never match, and surfacing
        # it as "not found" (rather than a distinct error) avoids leaking structure.
        canonical = OrderNumber(number).value
        return self._orders.get_for_owner(owner, canonical)


@dataclass(frozen=True)
class CancelMyOrderCommand:
    """Input for a shopper cancelling their own (still-pending) order."""

    owner: str
    number: str


class CancelMyOrder:
    """Cancel a still-pending order and return its captured stock, atomically.

    Only a ``pending`` order (placed, not yet paid) can be cancelled here: cancelling a
    paid order would require a refund, which belongs to a later phase. The status change
    and the restock happen inside one transaction and are audited.
    """

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        orders: OrderRepository,
        inventory: Inventory,
        audit: AuditRecorder,
    ) -> None:
        self._uow = unit_of_work
        self._orders = orders
        self._inventory = inventory
        self._audit = audit

    def execute(self, command: CancelMyOrderCommand) -> Order:
        canonical = OrderNumber(command.number).value
        with self._uow.atomic():
            order = self._orders.get_for_update(command.owner, canonical)
            if order.status is not OrderStatus.PENDING:
                raise OrderNotCancellableError(canonical, order.status.value)
            cancelled = order.cancel()
            for line in order.lines:
                self._inventory.restock(line.sku.value, line.quantity.value)
            saved = self._orders.set_status(cancelled, OrderStatus.CANCELLED)
            self._audit.record(
                action=_ACTION_ORDER_CANCELLED,
                resource_type=_RESOURCE_ORDER,
                resource_id=canonical,
                actor=command.owner,
                changes=(
                    FieldChange(
                        field="status",
                        before=OrderStatus.PENDING.value,
                        after=OrderStatus.CANCELLED.value,
                    ),
                ),
            )
        logger.info("order_cancelled", owner=command.owner, order_number=canonical)
        return saved
