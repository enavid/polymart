"""Django ORM implementation of the order ports.

The order repository persists and reloads the aggregate; the narrow adapters bridge to
the neighbouring cart, catalog, channel, and address contexts. All reads that a use
case uses to resolve an order are owner-scoped, so one shopper can never reach another's
order (or, via the address reader, capture another shopper's saved address).
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import Any

import structlog
from django.db import transaction

from src.application.inventory.use_cases import ReleaseReservation, ReserveStock
from src.application.order.ports import (
    AddressReader,
    CartForCheckout,
    ChannelReader,
    CheckoutLine,
    Inventory,
    OrderRepository,
    OwnedAddress,
    PricingReader,
    ProductTaxClassReader,
    ShippingQuote,
    ShippingRateReader,
    TaxCalculator,
    TaxQuote,
    UnitOfWork,
    VariantWeightReader,
)
from src.application.shipping.use_cases import GetShippingMethod
from src.application.tax.use_cases import CalculateTax
from src.domain.inventory.exceptions import (
    InsufficientStockError as InventoryInsufficientStockError,
)
from src.domain.order.entities import Order
from src.domain.order.exceptions import (
    OrderNotFoundError,
    OutOfStockError,
)
from src.domain.order.value_objects import Money, OrderStatus
from src.domain.shipping.exceptions import ShippingError, ShippingMethodNotFoundError
from src.domain.shipping.value_objects import Destination
from src.domain.tax.value_objects import Money as TaxMoney
from src.infrastructure.address.models import AddressModel
from src.infrastructure.cart.models import CartLineModel, CartModel
from src.infrastructure.catalog.models import ProductVariantModel, VariantPriceModel
from src.infrastructure.channel.models import ChannelModel
from src.infrastructure.inventory.repositories import DjangoStockLevelRepository
from src.infrastructure.order.mappers import order_to_domain
from src.infrastructure.order.models import OrderLineModel, OrderModel
from src.infrastructure.shipping.methods import SettingsShippingMethodReader
from src.infrastructure.tax.rates import SettingsTaxRateReader

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
        shipping = order.shipping
        tax = order.tax
        fulfillment = order.fulfillment
        model = OrderModel.objects.create(
            number=order.number.value,
            **_owner_filter(order.owner),
            channel_slug=order.channel.value,
            currency_code=order.currency,
            total=order.total.amount,
            shipping_cost=order.shipping_cost.amount,
            shipping_method_code=shipping.method_code if shipping is not None else "",
            shipping_method_name=shipping.method_name if shipping is not None else "",
            shipping_is_pickup=shipping.is_pickup if shipping is not None else False,
            # NULL rate is "no captured tax"; a captured tax (even at rate 0) stores both fields.
            tax_amount=tax.amount.amount if tax is not None else 0,
            tax_rate=tax.rate if tax is not None else None,
            status=order.status.value,
            placed_at=order.placed_at,
            # A pickup order captures no address; "" reads back as no captured address.
            shipping_recipient_name=address.recipient_name if address is not None else "",
            shipping_phone_number=address.phone_number if address is not None else "",
            shipping_province=address.province if address is not None else "",
            shipping_city=address.city if address is not None else "",
            shipping_postal_code=address.postal_code if address is not None else "",
            shipping_line1=address.line1 if address is not None else "",
            shipping_line2=(address.line2 or "") if address is not None else "",
            fulfillment_carrier=fulfillment.carrier if fulfillment is not None else "",
            fulfillment_tracking_number=(
                fulfillment.tracking_number if fulfillment is not None else ""
            ),
            fulfillment_tracking_url=(
                (fulfillment.tracking_url or "") if fulfillment is not None else ""
            ),
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

    def get_for_update_any(self, number: str) -> Order:
        # Staff fulfilment locks any order by number (not owner-scoped); reachable only
        # behind manage_orders. select_for_update serializes concurrent transitions.
        try:
            model = OrderModel.objects.select_for_update().get(number=number)
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
        # Persist the captured fulfilment alongside the status: shipping an order both
        # advances it to FULFILLED and records the carrier/tracking, in one write.
        fulfillment = order.fulfillment
        OrderModel.objects.filter(number=order.number.value).update(
            status=status.value,
            fulfillment_carrier=fulfillment.carrier if fulfillment is not None else "",
            fulfillment_tracking_number=(
                fulfillment.tracking_number if fulfillment is not None else ""
            ),
            fulfillment_tracking_url=(
                (fulfillment.tracking_url or "") if fulfillment is not None else ""
            ),
        )
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


class DjangoVariantWeightReader(VariantWeightReader):
    """Read variants' shipping weight (grams) from the catalog context, batched."""

    def weight_of(self, skus: Sequence[str]) -> dict[str, int]:
        if not skus:
            return {}
        rows = ProductVariantModel.objects.filter(sku__in=list(skus)).values_list(
            "sku", "weight_grams"
        )
        return {sku: int(weight) for sku, weight in rows}


class DjangoProductTaxClassReader(ProductTaxClassReader):
    """Read a variant's product tax class from the catalog context, batched."""

    def tax_class_of(self, skus: Sequence[str]) -> dict[str, str]:
        if not skus:
            return {}
        rows = ProductVariantModel.objects.filter(sku__in=list(skus)).values_list(
            "sku", "product__tax_class"
        )
        return dict(rows)


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


class ConfiguredShippingRateReader(ShippingRateReader):
    """Quote a chosen method by bridging to the shipping context.

    Implements the order context's narrow ``ShippingRateReader`` port by delegating to the
    shipping context's ``GetShippingMethod`` use case (over the settings-backed reader). A
    method the channel does not offer, or one whose configured currency does not match the
    resolved order currency, quotes ``None`` -- so checkout refuses it rather than capturing a
    mismatched or invented rate. No shipping-domain type crosses back: the result is the
    order context's own ``ShippingQuote``.
    """

    def __init__(self) -> None:
        self._methods = GetShippingMethod(SettingsShippingMethodReader())

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
        # A pickup (BOPIS) order captures no address, so province/city may be blank: quote
        # without a destination (no zoning -- pickup uses the method's default rate).
        destination: Destination | None = None
        if province:
            try:
                destination = Destination(province=province, city=city)
            except ShippingError:  # pragma: no cover - defensive
                # The destination comes from an already-validated ShippingAddress, so this is
                # a defensive guard; an unresolvable destination cannot be zoned, so refuse it.
                return None
        try:
            method = self._methods.execute(
                channel=channel, code=method_code, destination=destination
            )
        except ShippingMethodNotFoundError:
            return None
        # Resolve the actual cost for the order's weight (a weight-priced method picks its
        # bracket; a flat/zoned method ignores the weight and returns its resolved price).
        cost = method.quote(weight_grams)
        if cost.currency != currency:
            # A method priced in another currency cannot be added to this order's total.
            return None
        return ShippingQuote(
            method_code=method.code.value,
            method_name=method.name,
            cost=Money(amount=cost.amount, currency=cost.currency),
            is_pickup=method.is_pickup,
        )


class ConfiguredTaxCalculator(TaxCalculator):
    """Compute checkout tax by bridging to the tax context.

    Implements the order context's narrow ``TaxCalculator`` port by delegating to the tax
    context's ``CalculateTax`` use case (over the settings-backed rate reader). A channel that
    levies no tax calculates ``None`` -- so the order captures no tax line. No tax-domain type
    crosses back: the result is the order context's own ``TaxQuote``, and the amount is the tax
    context's computed value (never recomputed here).
    """

    def __init__(self) -> None:
        self._calculate = CalculateTax(SettingsTaxRateReader())

    def calculate(
        self, *, channel: str, taxable: Money, tax_class: str = "standard"
    ) -> TaxQuote | None:
        result = self._calculate.execute(
            channel=channel,
            taxable=TaxMoney(amount=taxable.amount, currency=taxable.currency),
            tax_class=tax_class,
        )
        if result is None:
            return None
        return TaxQuote(
            rate=result.rate.value,
            amount=Money(amount=result.amount.amount, currency=result.amount.currency),
        )


class DjangoInventory(Inventory):
    """Reserve/release stock via the inventory context's locked, multi-source model.

    Placing an order ``deduct``s -- which now *reserves* against available stock (the
    physical on-hand is untouched until fulfilment); cancelling ``restock``s, which
    *releases* the reservation. The inventory repository takes a row lock on the affected
    stock-level rows and refuses to reserve past available-to-promise (the anti-overselling
    guarantee). Inventory-domain errors are translated to order-domain errors so the
    boundary stays clean.
    """

    def __init__(self) -> None:
        repository = DjangoStockLevelRepository()
        self._reserve = ReserveStock(repository)
        self._release = ReleaseReservation(repository)

    def deduct(self, sku: str, quantity: int) -> None:
        try:
            self._reserve.execute(sku=sku, quantity=quantity)
        except InventoryInsufficientStockError as exc:
            raise OutOfStockError(sku, requested=quantity, available=exc.available) from exc

    def restock(self, sku: str, quantity: int) -> None:
        self._release.execute(sku=sku, quantity=quantity)


class DjangoUnitOfWork(UnitOfWork):
    """Transaction boundary backed by Django's ``transaction.atomic``.

    Everything a use case performs inside ``atomic()`` commits together or rolls back
    together on any exception -- the guarantee checkout relies on so an oversell reverts
    every earlier stock deduction and writes no order.
    """

    def atomic(self) -> AbstractContextManager[None]:
        return transaction.atomic()
