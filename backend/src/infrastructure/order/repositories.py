"""Django ORM implementation of the order ports.

The order repository persists and reloads the aggregate; the narrow adapters bridge to
the neighbouring cart, catalog, channel, and address contexts. All reads that a use
case uses to resolve an order are owner-scoped, so one shopper can never reach another's
order (or, via the address reader, capture another shopper's saved address).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

import structlog
from django.db import transaction

from src.application.order.ports import (
    AddressReader,
    CartForCheckout,
    ChannelReader,
    CheckoutLine,
    Inventory,
    OrderRepository,
    OwnedAddress,
    PricingReader,
    UnitOfWork,
)
from src.domain.catalog.exceptions import InsufficientStockError
from src.domain.catalog.exceptions import VariantNotFoundError as CatalogVariantNotFoundError
from src.domain.order.entities import Order
from src.domain.order.exceptions import (
    OrderNotFoundError,
    OutOfStockError,
    VariantNotFoundError,
)
from src.domain.order.value_objects import Money, OrderStatus
from src.infrastructure.address.models import AddressModel
from src.infrastructure.cart.models import CartLineModel, CartModel
from src.infrastructure.catalog.models import VariantPriceModel
from src.infrastructure.catalog.repositories import DjangoStockRepository
from src.infrastructure.channel.models import ChannelModel
from src.infrastructure.order.mappers import order_to_domain
from src.infrastructure.order.models import OrderLineModel, OrderModel

logger = structlog.get_logger(__name__)


def _owner_filter(owner: str) -> dict[str, Any]:
    """Map the application's opaque owner id to the order/cart columns that identify it.

    ``u:<pk>`` -> the user FK (``owner_id``); ``g:<token>`` -> the ``guest_token`` column.
    Mirrors the cart's decode and the encoding produced at the HTTP boundary (see
    ``src.interface.api.guest``); the split-on-colon contract is the only coupling, so the
    domain's stable string id stays independent of the database's key types.
    """
    kind, _, value = owner.partition(":")
    if kind == "u":
        return {"owner_id": int(value)}
    if kind == "g":
        return {"guest_token": value}
    raise ValueError(f"unrecognized order owner id: {owner!r}")  # pragma: no cover - defensive


def _user_pk_or_none(owner: str) -> int | None:
    """The user's integer pk for a ``u:<pk>`` owner, or ``None`` for a guest.

    A guest owns no address-book entries, so an address lookup for a guest owner has no
    row to find; returning ``None`` lets the reader answer "not found" without a decode
    error, exactly as a nonexistent saved address would.
    """
    kind, _, value = owner.partition(":")
    return int(value) if kind == "u" else None


class DjangoOrderRepository(OrderRepository):
    """Persist orders with the Django ORM, returning domain aggregates."""

    def add(self, order: Order) -> Order:
        address = order.shipping_address
        model = OrderModel.objects.create(
            number=order.number.value,
            **_owner_filter(order.owner),
            channel_slug=order.channel.value,
            currency_code=order.currency,
            total=order.total.amount,
            status=order.status.value,
            placed_at=order.placed_at,
            shipping_recipient_name=address.recipient_name,
            shipping_phone_number=address.phone_number,
            shipping_province=address.province,
            shipping_city=address.city,
            shipping_postal_code=address.postal_code,
            shipping_line1=address.line1,
            shipping_line2=address.line2 or "",
        )
        OrderLineModel.objects.bulk_create(
            OrderLineModel(
                order=model,
                sku=line.sku.value,
                quantity=line.quantity.value,
                unit_price=line.unit_price.amount,
                line_total=line.line_total.amount,
                position=position,
            )
            for position, line in enumerate(order.lines)
        )
        return self._load(model.number, owner=order.owner)

    def get(self, number: str) -> Order:
        # Not owner-scoped: only reachable behind the manage_orders permission (issuing a
        # pre-invoice for any order). Shopper reads always use the owner-scoped methods.
        try:
            model = OrderModel.objects.prefetch_related("lines").get(number=number)
        except OrderModel.DoesNotExist as exc:
            raise OrderNotFoundError(number) from exc
        return order_to_domain(model)

    def get_for_owner(self, owner: str, number: str) -> Order:
        return self._load(number, owner=owner)

    def get_for_update(self, owner: str, number: str) -> Order:
        # Lock the order row so two concurrent status changes (e.g. two cancels)
        # serialize instead of both reading a pending order.
        try:
            model = OrderModel.objects.select_for_update().get(
                number=number, **_owner_filter(owner)
            )
        except OrderModel.DoesNotExist as exc:
            raise OrderNotFoundError(number) from exc
        return order_to_domain(model)

    def list_for_owner(
        self, owner: str, *, limit: int, offset: int
    ) -> tuple[tuple[Order, ...], int]:
        base = OrderModel.objects.filter(**_owner_filter(owner)).prefetch_related("lines")
        total = base.count()
        # Meta.ordering is already newest-first ("-id").
        rows = list(base[offset : offset + limit])
        return tuple(order_to_domain(row) for row in rows), total

    def set_status(self, order: Order, status: OrderStatus) -> Order:
        OrderModel.objects.filter(number=order.number.value).update(status=status.value)
        return self._load(order.number.value, owner=order.owner)

    @staticmethod
    def _load(number: str, *, owner: str) -> Order:
        try:
            model = OrderModel.objects.prefetch_related("lines").get(
                number=number, **_owner_filter(owner)
            )
        except OrderModel.DoesNotExist as exc:
            raise OrderNotFoundError(number) from exc
        return order_to_domain(model)


class DjangoCartForCheckout(CartForCheckout):
    """Read and clear the owner's cart, bridging to the cart context's models."""

    def line_items(self, owner: str, channel: str) -> tuple[CheckoutLine, ...]:
        cart = CartModel.objects.filter(**_owner_filter(owner), channel_slug=channel).first()
        if cart is None:
            return ()
        rows = cart.lines.all().order_by("position").values_list("sku", "quantity")
        return tuple(CheckoutLine(sku=sku, quantity=quantity) for sku, quantity in rows)

    def clear(self, owner: str, channel: str) -> None:
        # Delete the cart's lines (the row is left, so a fresh read returns an empty
        # cart). Runs inside the checkout unit of work, so it commits with the order.
        cart = CartModel.objects.filter(**_owner_filter(owner), channel_slug=channel).first()
        if cart is not None:
            CartLineModel.objects.filter(cart=cart).delete()


class DjangoPricingReader(PricingReader):
    """Capture a variant's current channel price from the catalog context."""

    def price_of(self, sku: str, channel: str) -> Money | None:
        row = VariantPriceModel.objects.filter(variant__sku=sku, channel_slug=channel).first()
        if row is None:
            return None
        return Money(amount=row.amount, currency=row.currency_code)


class DjangoAddressReader(AddressReader):
    """Read a shopper's saved address from the address context, for checkout capture.

    Owner-scoped: an address_id belonging to another owner (or that does not exist at
    all) resolves to ``None``, exactly like a wrong-shaped one, so checkout can never
    ship to someone else's saved address.
    """

    def get_for_owner(self, owner: str, address_id: str) -> OwnedAddress | None:
        owner_pk = _user_pk_or_none(owner)
        if owner_pk is None:
            # A guest has no saved addresses; nothing to resolve (they check out inline).
            return None
        row = AddressModel.objects.filter(address_id=address_id, owner_id=owner_pk).first()
        if row is None:
            return None
        return OwnedAddress(
            recipient_name=row.recipient_name,
            phone_number=row.phone_number,
            province=row.province,
            city=row.city,
            postal_code=row.postal_code,
            line1=row.line1,
            line2=row.line2 or None,
        )


class DjangoChannelReader(ChannelReader):
    """Read a channel's currency from the channel context, for the order currency."""

    def currency_of(self, channel: str) -> str | None:
        return (
            ChannelModel.objects.filter(slug=channel)
            .values_list("currency_code", flat=True)
            .first()
        )


class DjangoInventory(Inventory):
    """Move on-hand stock via the catalog's locked, no-below-zero stock repository.

    ``deduct`` is a negative adjustment; the catalog repository takes a row lock and
    refuses to drop below zero (the anti-overselling guarantee). Catalog-domain errors
    are translated to order-domain errors so the boundary stays clean.
    """

    def __init__(self) -> None:
        self._stock = DjangoStockRepository()

    def deduct(self, sku: str, quantity: int) -> None:
        try:
            self._stock.adjust_quantity(sku, -quantity)
        except InsufficientStockError as exc:
            raise OutOfStockError(sku, requested=quantity, available=exc.available) from exc
        except CatalogVariantNotFoundError as exc:
            raise VariantNotFoundError(sku) from exc

    def restock(self, sku: str, quantity: int) -> None:
        try:
            self._stock.adjust_quantity(sku, quantity)
        except CatalogVariantNotFoundError as exc:  # pragma: no cover - defensive
            raise VariantNotFoundError(sku) from exc


class DjangoUnitOfWork(UnitOfWork):
    """Transaction boundary backed by Django's ``transaction.atomic``.

    Everything a use case performs inside ``atomic()`` commits together or rolls back
    together on any exception -- the guarantee checkout relies on so an oversell reverts
    every earlier stock deduction and writes no order.
    """

    def atomic(self) -> AbstractContextManager[None]:
        return transaction.atomic()
