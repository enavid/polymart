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

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import structlog

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
    OrderPage,
    OrderRepository,
    OwnedAddress,
    PricingReader,
    ProductTaxClassReader,
    ShippingQuote,
    ShippingRateReader,
    TaxCalculator,
    UnitOfWork,
    VariantWeightReader,
)
from src.application.shared.events import EventPublisher
from src.application.shared.owner import safe_owner
from src.domain.audit.entities import FieldChange
from src.domain.order.entities import Order, OrderLine
from src.domain.order.events import OrderPlaced
from src.domain.order.exceptions import (
    EmptyCartError,
    FulfillmentMethodMismatchError,
    OrderNotCancellableError,
    UnknownChannelError,
    UnknownShippingAddressError,
    UnknownShippingMethodError,
    VariantNotPurchasableError,
)
from src.domain.order.services import PricedItem, build_order_lines, order_total
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

logger = structlog.get_logger(__name__)

# Pagination bounds for a shopper's order history, mirroring the catalog/access read
# windows so a caller cannot ask for an unbounded page.
DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100

_RESOURCE_ORDER = "order"
_ACTION_ORDER_PLACED = "order.placed"
_ACTION_ORDER_CANCELLED = "order.cancelled"
_ACTION_ORDER_CREATED_MANUALLY = "order.created_manually"
_ACTION_ORDER_SHIPPED = "order.shipped"
_ACTION_ORDER_READY_FOR_PICKUP = "order.ready_for_pickup"
_ACTION_ORDER_PICKED_UP = "order.picked_up"


class InvalidOrderPageError(Exception):
    """Raised when the requested order-history page window is out of range."""


def _resolve_currency(channels: ChannelReader, channel: str) -> str:
    currency = channels.currency_of(channel)
    if currency is None:
        raise UnknownChannelError(channel)
    return currency


def _resolve_shipping_address(
    addresses: AddressReader, owner: str, address_id: str
) -> ShippingAddress:
    owned = addresses.get_for_owner(owner, address_id)
    if owned is None:
        raise UnknownShippingAddressError(address_id)
    return _to_shipping_address(owned)


def _capture_and_deduct(
    items: Sequence[tuple[str, int]],
    channel: str,
    currency: str,
    *,
    pricing: PricingReader,
    inventory: Inventory,
) -> list[PricedItem]:
    """Capture each item's current price and deduct its stock (inside the caller's txn).

    Shared by checkout (cart-sourced items) and manual order creation (staff-supplied
    items). A line whose variant has no price in the channel is refused (it could not be
    sold); ``inventory.deduct`` refuses an oversell. Because the caller runs this inside
    a unit of work, a failure on any line rolls back the deductions already made.
    """
    priced: list[PricedItem] = []
    for raw_sku, raw_quantity in items:
        sku = Sku(raw_sku)
        quantity = OrderQuantity(raw_quantity)
        unit_price = pricing.price_of(sku.value, channel)
        if unit_price is None:
            raise VariantNotPurchasableError(sku.value, channel)
        if unit_price.currency != currency:  # pragma: no cover - defensive
            raise VariantNotPurchasableError(sku.value, channel)
        inventory.deduct(sku.value, quantity.value)
        priced.append(PricedItem(sku=sku, quantity=quantity, unit_price=unit_price))
    return priced


def _resolve_captured_tax(
    tax: TaxCalculator,
    channel: str,
    currency: str,
    lines: tuple[OrderLine, ...],
    shipping_cost: Money,
    class_by_sku: dict[str, str],
) -> CapturedTax | None:
    """Compute the order's tax per line by the product's tax class, and capture the total.

    Each line is taxed at its product's tax class (an exempt product contributes nothing);
    shipping is taxed at the ``standard`` class. Each amount is computed by the tax context
    (with its rounding rule) and summed, so the captured amount is authoritative and the order
    never recomputes it from a rate. ``None`` means no tax at all (an untaxed channel, or an
    all-exempt order). The captured ``rate`` is the headline (highest) rate applied -- the label
    shown on the order; a mixed-class order's exact tax lives in the amount, not the rate.
    Shared by checkout and manual order creation.
    """
    total = Money.zero(currency)
    applied_rates: set[Decimal] = set()
    for line in lines:
        tax_class = class_by_sku.get(line.sku.value, "standard")
        quote = tax.calculate(channel=channel, taxable=line.line_total, tax_class=tax_class)
        if quote is not None:
            total = total.add(quote.amount)
            applied_rates.add(quote.rate)
    if shipping_cost.amount > 0:
        ship_quote = tax.calculate(channel=channel, taxable=shipping_cost, tax_class="standard")
        if ship_quote is not None:
            total = total.add(ship_quote.amount)
            applied_rates.add(ship_quote.rate)
    if not applied_rates:
        return None
    return CapturedTax(rate=max(applied_rates), amount=total)


def _tax_amount(captured_tax: CapturedTax | None) -> Money | None:
    """The captured tax amount for the total maths, or ``None`` when the order is untaxed."""
    return captured_tax.amount if captured_tax is not None else None


def _to_shipping_address(owned: OwnedAddress | InlineShippingAddress) -> ShippingAddress:
    return ShippingAddress(
        recipient_name=owned.recipient_name,
        phone_number=owned.phone_number,
        province=owned.province,
        city=owned.city,
        postal_code=owned.postal_code,
        line1=owned.line1,
        line2=owned.line2,
    )


@dataclass(frozen=True)
class PlaceOrderCommand:
    """Input for turning a shopper's cart into a placed order.

    The shipping address arrives one of two ways, exactly one of which is set: a signed-in
    shopper picks a saved ``address_id`` (resolved from their address book), while a guest
    supplies a one-off ``shipping_address`` inline (they have no book). Supplying neither
    is rejected as an unknown address.

    ``shipping_method`` is the code of the chosen delivery method (e.g. ``"standard"``); its
    cost is *quoted* from the channel's configured rates and captured onto the order. The
    transport requires it, so it is always supplied by a real request.
    """

    owner: str
    channel: str
    shipping_method: str
    address_id: str | None = None
    shipping_address: InlineShippingAddress | None = None


class PlaceOrder:
    """Convert the owner's cart in a channel into a placed order, atomically.

    Prices are *captured* from the current catalog price (a snapshot), the shipping
    address is *captured* from the owner's address book (also a snapshot), stock is
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
        weights: VariantWeightReader,
        channels: ChannelReader,
        addresses: AddressReader,
        shipping: ShippingRateReader,
        tax: TaxCalculator,
        tax_classes: ProductTaxClassReader,
        inventory: Inventory,
        orders: OrderRepository,
        numbers: OrderNumberGenerator,
        clock: Clock,
        audit: AuditRecorder,
        events: EventPublisher,
    ) -> None:
        self._uow = unit_of_work
        self._carts = carts
        self._pricing = pricing
        self._weights = weights
        self._channels = channels
        self._addresses = addresses
        self._shipping = shipping
        self._tax = tax
        self._tax_classes = tax_classes
        self._inventory = inventory
        self._orders = orders
        self._numbers = numbers
        self._clock = clock
        self._audit = audit
        self._events = events

    def execute(self, command: PlaceOrderCommand) -> Order:
        channel = ChannelRef(command.channel)
        currency = _resolve_currency(self._channels, channel.value)
        # Resolve the address if one was supplied (a pickup order supplies none). The method is
        # quoted inside the transaction, once the cart is read, because a weight-priced method
        # needs the order's total weight to pick its rate bracket.
        shipping_address = self._resolve_shipping_optional(command)

        with self._uow.atomic():
            items = self._carts.line_items(command.owner, channel.value)
            if not items:
                raise EmptyCartError(channel.value)

            weight = self._order_weight(items)
            quote = self._resolve_shipping_quote(
                channel.value, command.shipping_method, currency, shipping_address, weight
            )
            if quote.is_pickup:
                # A pickup (BOPIS) order is collected in store: it captures no shipping address.
                shipping_address = None
            elif shipping_address is None:
                # A delivery method must ship somewhere; refused like an unknown address.
                raise UnknownShippingAddressError("")
            captured_shipping = CapturedShipping(
                method_code=quote.method_code,
                method_name=quote.method_name,
                cost=quote.cost,
                is_pickup=quote.is_pickup,
            )

            priced_items = _capture_and_deduct(
                [(item.sku, item.quantity) for item in items],
                channel.value,
                currency,
                pricing=self._pricing,
                inventory=self._inventory,
            )
            lines = build_order_lines(priced_items)
            # Tax is resolved per line by the product's tax class (exempt lines pay none) plus
            # shipping at the standard class, and the computed total is captured onto the order.
            class_by_sku = self._tax_classes.tax_class_of([line.sku.value for line in lines])
            captured_tax = _resolve_captured_tax(
                self._tax, channel.value, currency, lines, captured_shipping.cost, class_by_sku
            )
            total = order_total(lines, currency, captured_shipping.cost, _tax_amount(captured_tax))
            order = Order(
                number=self._numbers.next(),
                owner=command.owner,
                channel=channel,
                currency=currency,
                lines=lines,
                total=total,
                status=OrderStatus.PENDING,
                placed_at=self._clock.now(),
                shipping_address=shipping_address,
                shipping=captured_shipping,
                tax=captured_tax,
            )
            saved = self._orders.add(order)
            self._carts.clear(command.owner, channel.value)
            self._audit.record(
                action=_ACTION_ORDER_PLACED,
                resource_type=_RESOURCE_ORDER,
                resource_id=saved.number.value,
                actor=safe_owner(command.owner),
                changes=(
                    FieldChange(field="status", after=OrderStatus.PENDING.value),
                    FieldChange(field="total", after=str(total.amount)),
                    FieldChange(field="shipping_method", after=captured_shipping.method_code),
                    FieldChange(field="shipping_cost", after=str(captured_shipping.cost.amount)),
                    FieldChange(field="tax", after=str(order.tax_amount.amount)),
                    FieldChange(field="line_count", after=len(lines)),
                ),
            )
            # Announce the placement on the event bus. Published inside the transaction so
            # the adapter's after-commit delivery is discarded if the order rolls back; a
            # subscriber (a confirmation, fulfilment) therefore never fires for a lost order.
            self._events.publish(
                OrderPlaced(
                    occurred_at=order.placed_at,
                    order_number=saved.number.value,
                    owner=command.owner,
                    channel=channel.value,
                    currency=currency,
                    total=total.amount,
                    line_count=len(lines),
                )
            )

        # Logged outside the money detail: number and shape, never the amount. The owner
        # is redacted so a guest's session token never reaches the logs (see safe_owner).
        logger.info(
            "order_placed",
            owner=safe_owner(command.owner),
            channel=channel.value,
            order_number=saved.number.value,
            line_count=len(lines),
            currency=currency,
        )
        return saved

    def _resolve_shipping_optional(self, command: PlaceOrderCommand) -> ShippingAddress | None:
        """Resolve the captured shipping address if one was supplied, else ``None``.

        An inline address (a guest's one-off form) is captured directly; otherwise a saved
        ``address_id`` is resolved from the owner's book. Supplying neither yields ``None`` --
        legal for a pickup (BOPIS) order; a delivery order without an address is refused by
        the caller once the method's kind is known.
        """
        if command.shipping_address is not None:
            return _to_shipping_address(command.shipping_address)
        if command.address_id is not None:
            return _resolve_shipping_address(self._addresses, command.owner, command.address_id)
        return None

    def _order_weight(self, items: Sequence[CheckoutLine]) -> int:
        """Total shipping weight (grams) of the cart: each variant's weight times its quantity.

        Looked up from the catalog through a narrow port; an unweighed variant contributes 0,
        so a catalog with no weights behaves exactly as the flat-rate case.
        """
        by_sku = self._weights.weight_of([item.sku for item in items])
        return sum(by_sku.get(item.sku, 0) * item.quantity for item in items)

    def _resolve_shipping_quote(
        self,
        channel: str,
        method_code: str,
        currency: str,
        address: ShippingAddress | None,
        weight_grams: int,
    ) -> ShippingQuote:
        """Quote the chosen shipping method, or refuse a method the channel does not offer.

        Priced server-side for the captured destination *and* the order's weight, so the rate
        re-resolves from the address and the real cart rather than trusting whatever the client
        was shown. A pickup order has no address, so the destination is blank (no zoning -- the
        method's default rate). An unknown or currency-mismatched method never commits.
        """
        quote = self._shipping.quote(
            channel=channel,
            method_code=method_code,
            currency=currency,
            province=address.province if address is not None else "",
            city=address.city if address is not None else "",
            weight_grams=weight_grams,
        )
        if quote is None:
            raise UnknownShippingMethodError(channel, method_code)
        return quote


@dataclass(frozen=True)
class ManualOrderItem:
    """One staff-specified line of a manual order (a sku and how many)."""

    sku: str
    quantity: int


@dataclass(frozen=True)
class CreateManualOrderCommand:
    """Input for a staff member creating a manual order (a pre-invoice).

    ``actor`` is the creating staff's owner id (``u:<pk>``); the manual order is owned by
    them (so they can read/manage it) and the customer is identified by the captured
    ``shipping_address`` (recipient + phone), matching the phone-first identity model.
    """

    actor: str
    channel: str
    items: tuple[ManualOrderItem, ...]
    shipping_address: InlineShippingAddress


class CreateManualOrder:
    """Create a pending order directly from staff-supplied lines (no cart), atomically.

    Behaves like checkout minus the cart: prices are *captured* from the current catalog,
    the shipping address is *captured* from the inline form, stock is deducted (refusing an
    oversell), the order is persisted PENDING, and the creation is audited -- all inside one
    transaction, so any failure leaves stock and trail exactly as they were. The pending
    order is the pre-invoice; payment (and a paid transition) belongs to a later phase.
    """

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        pricing: PricingReader,
        channels: ChannelReader,
        tax: TaxCalculator,
        tax_classes: ProductTaxClassReader,
        inventory: Inventory,
        orders: OrderRepository,
        numbers: OrderNumberGenerator,
        clock: Clock,
        audit: AuditRecorder,
        events: EventPublisher,
    ) -> None:
        self._uow = unit_of_work
        self._pricing = pricing
        self._channels = channels
        self._tax = tax
        self._tax_classes = tax_classes
        self._inventory = inventory
        self._orders = orders
        self._numbers = numbers
        self._clock = clock
        self._audit = audit
        self._events = events

    def execute(self, command: CreateManualOrderCommand) -> Order:
        channel = ChannelRef(command.channel)
        currency = _resolve_currency(self._channels, channel.value)
        shipping_address = _to_shipping_address(command.shipping_address)

        with self._uow.atomic():
            priced_items = _capture_and_deduct(
                [(item.sku, item.quantity) for item in command.items],
                channel.value,
                currency,
                pricing=self._pricing,
                inventory=self._inventory,
            )
            lines = build_order_lines(priced_items)
            # A manual order has no shipping charge, so tax applies to the goods lines alone,
            # each at its product's tax class (an exempt line pays none).
            class_by_sku = self._tax_classes.tax_class_of([line.sku.value for line in lines])
            captured_tax = _resolve_captured_tax(
                self._tax, channel.value, currency, lines, Money.zero(currency), class_by_sku
            )
            total = order_total(lines, currency, None, _tax_amount(captured_tax))
            # An empty line list can build no order (EmptyOrderError from the aggregate)
            # and a repeated sku is rejected (DuplicateOrderLineError) -- both roll back.
            order = Order(
                number=self._numbers.next(),
                owner=command.actor,
                channel=channel,
                currency=currency,
                lines=lines,
                total=total,
                status=OrderStatus.PENDING,
                placed_at=self._clock.now(),
                shipping_address=shipping_address,
                tax=captured_tax,
            )
            saved = self._orders.add(order)
            self._audit.record(
                action=_ACTION_ORDER_CREATED_MANUALLY,
                resource_type=_RESOURCE_ORDER,
                resource_id=saved.number.value,
                actor=safe_owner(command.actor),
                changes=(
                    FieldChange(field="status", after=OrderStatus.PENDING.value),
                    FieldChange(field="total", after=str(total.amount)),
                    FieldChange(field="tax", after=str(order.tax_amount.amount)),
                    FieldChange(field="line_count", after=len(lines)),
                    FieldChange(field="origin", after="manual"),
                ),
            )
            # A manual order is a real placed order, so it announces the same OrderPlaced as
            # checkout (published in-transaction; discarded on rollback).
            self._events.publish(
                OrderPlaced(
                    occurred_at=order.placed_at,
                    order_number=saved.number.value,
                    owner=command.actor,
                    channel=channel.value,
                    currency=currency,
                    total=total.amount,
                    line_count=len(lines),
                )
            )

        logger.info(
            "manual_order_created",
            actor=safe_owner(command.actor),
            channel=channel.value,
            order_number=saved.number.value,
            line_count=len(lines),
            currency=currency,
        )
        return saved


class GetOrderForInvoice:
    """Read any order by number to issue its pre-invoice (behind the manage_orders perm).

    Unlike a shopper's own read, this is *not* owner-scoped: staff issuing a pre-invoice
    may print it for any order. The authorization is enforced at the transport by the
    ``manage_orders`` permission, so this use case trusts its caller.
    """

    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    def execute(self, *, number: str) -> Order:
        canonical = OrderNumber(number).value
        return self._orders.get(canonical)


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
        logger.debug(
            "orders_listed", owner=safe_owner(query.owner), count=total, returned=len(items)
        )
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
                actor=safe_owner(command.owner),
                changes=(
                    FieldChange(
                        field="status",
                        before=OrderStatus.PENDING.value,
                        after=OrderStatus.CANCELLED.value,
                    ),
                ),
            )
        logger.info("order_cancelled", owner=safe_owner(command.owner), order_number=canonical)
        return saved


@dataclass(frozen=True)
class ShipOrderCommand:
    """Input for staff shipping a paid delivery order (capture carrier + tracking)."""

    number: str
    carrier: str
    tracking_number: str
    tracking_url: str | None = None


class ShipOrder:
    """Ship a paid delivery order: capture the carrier/tracking and move to ``FULFILLED``.

    A staff (``manage_orders``) action, by order number, not owner-scoped. Row-locked so two
    concurrent transitions serialise. Refuses a pickup order (which uses the pickup path) and
    -- via the state machine -- any order not in ``PAID``. The captured shipment is audited.
    """

    def __init__(
        self, *, unit_of_work: UnitOfWork, orders: OrderRepository, audit: AuditRecorder
    ) -> None:
        self._uow = unit_of_work
        self._orders = orders
        self._audit = audit

    def execute(self, command: ShipOrderCommand, *, actor: str | None = None) -> Order:
        canonical = OrderNumber(command.number).value
        # Build the Fulfillment first so a malformed carrier/tracking fails before any lock.
        fulfillment = Fulfillment(
            carrier=command.carrier,
            tracking_number=command.tracking_number,
            tracking_url=command.tracking_url,
        )
        with self._uow.atomic():
            order = self._orders.get_for_update_any(canonical)
            if order.shipping is not None and order.shipping.is_pickup:
                raise FulfillmentMethodMismatchError(canonical, expected="pickup")
            shipped = order.ship(fulfillment)  # PAID -> FULFILLED (state machine guards it)
            saved = self._orders.set_status(shipped, OrderStatus.FULFILLED)
            self._audit.record(
                action=_ACTION_ORDER_SHIPPED,
                resource_type=_RESOURCE_ORDER,
                resource_id=canonical,
                actor=actor,
                changes=(
                    FieldChange(
                        field="status",
                        before=OrderStatus.PAID.value,
                        after=OrderStatus.FULFILLED.value,
                    ),
                    FieldChange(field="carrier", after=fulfillment.carrier),
                    FieldChange(field="tracking_number", after=fulfillment.tracking_number),
                ),
            )
        logger.info(
            "order_shipped",
            order_number=canonical,
            carrier=fulfillment.carrier,
            actor=actor,
        )
        return saved


@dataclass(frozen=True)
class FulfillmentActionCommand:
    """Input for a staff pickup transition (ready-for-pickup / confirm-pickup) by number."""

    number: str


class MarkOrderReadyForPickup:
    """Move a paid pickup (BOPIS) order to ``READY_FOR_PICKUP`` (staff, ``manage_orders``).

    Row-locked; refuses a delivery order (which ships instead) and -- via the state machine --
    any order not in ``PAID``. Audited.
    """

    def __init__(
        self, *, unit_of_work: UnitOfWork, orders: OrderRepository, audit: AuditRecorder
    ) -> None:
        self._uow = unit_of_work
        self._orders = orders
        self._audit = audit

    def execute(self, command: FulfillmentActionCommand, *, actor: str | None = None) -> Order:
        canonical = OrderNumber(command.number).value
        with self._uow.atomic():
            order = self._orders.get_for_update_any(canonical)
            if order.shipping is None or not order.shipping.is_pickup:
                raise FulfillmentMethodMismatchError(canonical, expected="delivery")
            ready = order.mark_ready_for_pickup()
            saved = self._orders.set_status(ready, OrderStatus.READY_FOR_PICKUP)
            self._audit.record(
                action=_ACTION_ORDER_READY_FOR_PICKUP,
                resource_type=_RESOURCE_ORDER,
                resource_id=canonical,
                actor=actor,
                changes=(
                    FieldChange(
                        field="status",
                        before=OrderStatus.PAID.value,
                        after=OrderStatus.READY_FOR_PICKUP.value,
                    ),
                ),
            )
        logger.info("order_ready_for_pickup", order_number=canonical, actor=actor)
        return saved


class ConfirmOrderPickup:
    """Move a ready pickup order to ``PICKED_UP`` (staff, ``manage_orders``).

    Row-locked; the state machine allows this only from ``READY_FOR_PICKUP``. Audited.
    """

    def __init__(
        self, *, unit_of_work: UnitOfWork, orders: OrderRepository, audit: AuditRecorder
    ) -> None:
        self._uow = unit_of_work
        self._orders = orders
        self._audit = audit

    def execute(self, command: FulfillmentActionCommand, *, actor: str | None = None) -> Order:
        canonical = OrderNumber(command.number).value
        with self._uow.atomic():
            order = self._orders.get_for_update_any(canonical)
            picked_up = order.confirm_pickup()
            saved = self._orders.set_status(picked_up, OrderStatus.PICKED_UP)
            self._audit.record(
                action=_ACTION_ORDER_PICKED_UP,
                resource_type=_RESOURCE_ORDER,
                resource_id=canonical,
                actor=actor,
                changes=(
                    FieldChange(
                        field="status",
                        before=OrderStatus.READY_FOR_PICKUP.value,
                        after=OrderStatus.PICKED_UP.value,
                    ),
                ),
            )
        logger.info("order_picked_up", order_number=canonical, actor=actor)
        return saved
