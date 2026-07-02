"""End-to-end integration tests for checkout against the real stack (DB + adapters).

This is the money/inventory-critical path, so it is tested with the real Django
adapters wired together (no fakes): the Unit of Work, the locked stock repository, the
order repository, the cart bridge, and the durable audit trail. The decisive test is
that an oversell on one line rolls back the stock deduction already made on an earlier
line -- the multi-aggregate atomicity guarantee.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from src.application.order.ports import OrderNumberGenerator
from src.application.order.use_cases import (
    CancelMyOrder,
    CancelMyOrderCommand,
    PlaceOrder,
    PlaceOrderCommand,
)
from src.domain.cart.value_objects import CartQuantity
from src.domain.cart.value_objects import Sku as CartSku
from src.domain.catalog.entities import Product, ProductType, ProductVariant
from src.domain.catalog.value_objects import (
    ChannelPrice,
    ProductCode,
    ProductTypeCode,
    StockQuantity,
)
from src.domain.catalog.value_objects import Money as CatalogMoney
from src.domain.catalog.value_objects import Sku as CatalogSku
from src.domain.channel.entities import Channel
from src.domain.channel.value_objects import ChannelSlug, Currency
from src.domain.order.exceptions import EmptyCartError, OrderNotFoundError, OutOfStockError
from src.domain.order.value_objects import OrderNumber, OrderStatus
from src.infrastructure.audit.models import AuditLogModel
from src.infrastructure.cart.repositories import DjangoCartRepository
from src.infrastructure.catalog.repositories import (
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoStockRepository,
    DjangoVariantPriceRepository,
    DjangoVariantRepository,
)
from src.infrastructure.channel.repositories import DjangoChannelRepository
from src.infrastructure.order.clock import SystemClock
from src.infrastructure.order.repositories import (
    DjangoCartForCheckout,
    DjangoChannelReader,
    DjangoInventory,
    DjangoOrderRepository,
    DjangoPricingReader,
    DjangoUnitOfWork,
)
from src.interface.api.audit.container import build_audit_recorder

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CHANNEL = "ir-main"


class _FixedNumbers(OrderNumberGenerator):
    """Deterministic order numbers so integration assertions are stable."""

    def __init__(self, *values: str) -> None:
        self._values = list(values) or ["ORD-INTEG000001"]
        self._index = 0

    def next(self) -> OrderNumber:
        value = self._values[min(self._index, len(self._values) - 1)]
        self._index += 1
        return OrderNumber(value)


def _seed_catalog() -> None:
    DjangoChannelRepository().add(
        Channel(slug=ChannelSlug(_CHANNEL), name="Iran Main", currency=Currency("IRR"))
    )
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
    DjangoProductRepository().add(
        Product(code=ProductCode("house-blend"), name="H", product_type=ProductTypeCode("coffee"))
    )
    _seed_variant("HB-250", "120000.00", stock=5)
    _seed_variant("DR-250", "150000.00", stock=1)


def _seed_variant(sku: str, price: str, *, stock: int) -> None:
    DjangoVariantRepository().add(
        ProductVariant(product=ProductCode("house-blend"), sku=CatalogSku(sku), name="v")
    )
    DjangoVariantPriceRepository().replace(
        sku,
        (
            ChannelPrice(
                channel=_CHANNEL, money=CatalogMoney(amount=Decimal(price), currency="IRR")
            ),
        ),
    )
    DjangoStockRepository().set_quantity(sku, StockQuantity(stock))


def _add_to_cart(owner: str, sku: str, quantity: int) -> None:
    DjangoCartRepository().apply(
        owner, _CHANNEL, lambda cart: cart.add_item(CartSku(sku), CartQuantity(quantity))
    )


def _place_order(numbers: OrderNumberGenerator | None = None) -> PlaceOrder:
    return PlaceOrder(
        unit_of_work=DjangoUnitOfWork(),
        carts=DjangoCartForCheckout(),
        pricing=DjangoPricingReader(),
        channels=DjangoChannelReader(),
        inventory=DjangoInventory(),
        orders=DjangoOrderRepository(),
        numbers=numbers or _FixedNumbers(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
    )


class TestCheckoutHappyPath:
    def test_places_an_order_deducts_stock_clears_cart_and_audits(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = str(user.pk)
        _add_to_cart(owner, "HB-250", 2)
        _add_to_cart(owner, "DR-250", 1)

        order = _place_order().execute(PlaceOrderCommand(owner=owner, channel=_CHANNEL))

        # Order persisted with the captured total.
        assert order.total.amount == Decimal("390000.00")
        assert order.status is OrderStatus.PENDING
        assert DjangoOrderRepository().get_for_owner(owner, order.number.value).id == order.id
        # Stock deducted for both lines.
        assert DjangoStockRepository().get_quantity("HB-250").value == 3
        assert DjangoStockRepository().get_quantity("DR-250").value == 0
        # Cart cleared.
        assert DjangoCartForCheckout().line_items(owner, _CHANNEL) == ()
        # Placement audited durably.
        assert AuditLogModel.objects.filter(
            action="order.placed", resource_id=order.number.value
        ).exists()


class TestCheckoutAtomicity:
    def test_an_oversell_rolls_back_the_whole_checkout(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = str(user.pk)
        # First line deducts fine; the second oversells DR-250 (only 1 in stock).
        _add_to_cart(owner, "HB-250", 2)
        _add_to_cart(owner, "DR-250", 5)

        with pytest.raises(OutOfStockError):
            _place_order().execute(PlaceOrderCommand(owner=owner, channel=_CHANNEL))

        # Nothing committed: no order, the earlier deduction reverted, cart intact.
        assert DjangoOrderRepository().list_for_owner(owner, limit=10, offset=0) == ((), 0)
        assert DjangoStockRepository().get_quantity("HB-250").value == 5
        assert DjangoStockRepository().get_quantity("DR-250").value == 1
        assert len(DjangoCartForCheckout().line_items(owner, _CHANNEL)) == 2
        assert not AuditLogModel.objects.filter(action="order.placed").exists()

    def test_an_empty_cart_places_nothing(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = str(user.pk)

        with pytest.raises(EmptyCartError):
            _place_order().execute(PlaceOrderCommand(owner=owner, channel=_CHANNEL))
        assert DjangoOrderRepository().list_for_owner(owner, limit=10, offset=0) == ((), 0)


class TestCancelIntegration:
    def test_cancel_restocks_and_is_audited(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = str(user.pk)
        _add_to_cart(owner, "HB-250", 2)
        order = _place_order().execute(PlaceOrderCommand(owner=owner, channel=_CHANNEL))
        assert DjangoStockRepository().get_quantity("HB-250").value == 3

        cancel = CancelMyOrder(
            unit_of_work=DjangoUnitOfWork(),
            orders=DjangoOrderRepository(),
            inventory=DjangoInventory(),
            audit=build_audit_recorder(),
        )
        result = cancel.execute(CancelMyOrderCommand(owner=owner, number=order.number.value))

        assert result.status is OrderStatus.CANCELLED
        assert DjangoStockRepository().get_quantity("HB-250").value == 5  # restored
        assert AuditLogModel.objects.filter(
            action="order.cancelled", resource_id=order.number.value
        ).exists()

    def test_cancel_is_owner_scoped(self) -> None:
        _seed_catalog()
        owner = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        intruder = get_user_model().objects.create_user(phone_number="09120000002", password="pw")
        _add_to_cart(str(owner.pk), "HB-250", 1)
        order = _place_order().execute(PlaceOrderCommand(owner=str(owner.pk), channel=_CHANNEL))

        cancel = CancelMyOrder(
            unit_of_work=DjangoUnitOfWork(),
            orders=DjangoOrderRepository(),
            inventory=DjangoInventory(),
            audit=build_audit_recorder(),
        )
        with pytest.raises(OrderNotFoundError):
            cancel.execute(CancelMyOrderCommand(owner=str(intruder.pk), number=order.number.value))
        # The order is untouched and stock stays deducted.
        assert DjangoStockRepository().get_quantity("HB-250").value == 4
