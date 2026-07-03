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

from src.application.order.ports import InlineShippingAddress, OrderNumberGenerator
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
    DjangoAddressReader,
    DjangoCartForCheckout,
    DjangoChannelReader,
    DjangoInventory,
    DjangoOrderRepository,
    DjangoPricingReader,
    DjangoUnitOfWork,
)
from src.interface.api.audit.container import build_audit_recorder
from tests.integration.order.factories import seed_address

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CHANNEL = "ir-main"
_ADDRESS_ID = "ADDR-SHIP000001"


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


def _owner(user: object) -> str:
    """The prefixed owner id the cart/order contexts key a signed-in user by."""
    return f"u:{user.pk}"


def _add_to_cart(owner: str, sku: str, quantity: int) -> None:
    # Seed the cart exactly as the cart endpoints store it: keyed by the prefixed owner
    # id (``u:<pk>`` for a user, ``g:<token>`` for a guest). The order checkout reads it
    # back by the same key, so a user and a guest seed identically here.
    DjangoCartRepository().apply(
        owner, _CHANNEL, lambda cart: cart.add_item(CartSku(sku), CartQuantity(quantity))
    )


def _place_order(numbers: OrderNumberGenerator | None = None) -> PlaceOrder:
    return PlaceOrder(
        unit_of_work=DjangoUnitOfWork(),
        carts=DjangoCartForCheckout(),
        pricing=DjangoPricingReader(),
        channels=DjangoChannelReader(),
        addresses=DjangoAddressReader(),
        inventory=DjangoInventory(),
        orders=DjangoOrderRepository(),
        numbers=numbers or _FixedNumbers(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
    )


def _checkout_command(owner: str) -> PlaceOrderCommand:
    return PlaceOrderCommand(owner=owner, channel=_CHANNEL, address_id=_ADDRESS_ID)


class TestCheckoutHappyPath:
    def test_places_an_order_deducts_stock_clears_cart_and_audits(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        _add_to_cart(owner, "HB-250", 2)
        _add_to_cart(owner, "DR-250", 1)

        order = _place_order().execute(_checkout_command(owner))

        # Order persisted with the captured total.
        assert order.total.amount == Decimal("390000.00")
        assert order.status is OrderStatus.PENDING
        assert DjangoOrderRepository().get_for_owner(owner, order.number.value).id == order.id
        # The shipping address was captured from the shopper's address book.
        assert order.shipping_address.recipient_name == "Sara Ahmadi"
        # Stock deducted for both lines.
        assert DjangoStockRepository().get_quantity("HB-250").value == 3
        assert DjangoStockRepository().get_quantity("DR-250").value == 0
        # Cart cleared.
        assert DjangoCartForCheckout().line_items(owner, _CHANNEL) == ()
        # Placement audited durably.
        assert AuditLogModel.objects.filter(
            action="order.placed", resource_id=order.number.value
        ).exists()


class TestGuestCheckoutIntegration:
    def test_a_guest_checks_out_with_an_inline_address_through_the_real_stack(self) -> None:
        # No user, no address book: the guest's cart is keyed by a session token and the
        # shipping address is captured inline. Exercises the real cart bridge reading a
        # ``g:`` cart and the order repository writing a guest_token row.
        _seed_catalog()
        owner = "g:guest-token-integ"
        _add_to_cart(owner, "HB-250", 2)

        order = _place_order().execute(
            PlaceOrderCommand(
                owner=owner,
                channel=_CHANNEL,
                shipping_address=InlineShippingAddress(
                    recipient_name="Guest Buyer",
                    phone_number="09121112233",
                    province="Isfahan",
                    city="Isfahan",
                    postal_code="8134567890",
                    line1="Chaharbagh St, No. 9",
                    line2=None,
                ),
            )
        )

        assert order.owner == owner
        assert order.total.amount == Decimal("240000.00")
        assert order.shipping_address.recipient_name == "Guest Buyer"
        assert DjangoOrderRepository().get_for_owner(owner, order.number.value).id == order.id
        assert DjangoStockRepository().get_quantity("HB-250").value == 3
        assert DjangoCartForCheckout().line_items(owner, _CHANNEL) == ()


class TestCheckoutAtomicity:
    def test_an_oversell_rolls_back_the_whole_checkout(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        # First line deducts fine; the second oversells DR-250 (only 1 in stock).
        _add_to_cart(owner, "HB-250", 2)
        _add_to_cart(owner, "DR-250", 5)

        with pytest.raises(OutOfStockError):
            _place_order().execute(_checkout_command(owner))

        # Nothing committed: no order, the earlier deduction reverted, cart intact.
        assert DjangoOrderRepository().list_for_owner(owner, limit=10, offset=0) == ((), 0)
        assert DjangoStockRepository().get_quantity("HB-250").value == 5
        assert DjangoStockRepository().get_quantity("DR-250").value == 1
        assert len(DjangoCartForCheckout().line_items(owner, _CHANNEL)) == 2
        assert not AuditLogModel.objects.filter(action="order.placed").exists()

    def test_an_empty_cart_places_nothing(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)

        with pytest.raises(EmptyCartError):
            _place_order().execute(_checkout_command(owner))
        assert DjangoOrderRepository().list_for_owner(owner, limit=10, offset=0) == ((), 0)


class TestCancelIntegration:
    def test_cancel_restocks_and_is_audited(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        _add_to_cart(owner, "HB-250", 2)
        order = _place_order().execute(_checkout_command(owner))
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
        seed_address(owner.pk)
        _add_to_cart(_owner(owner), "HB-250", 1)
        order = _place_order().execute(_checkout_command(_owner(owner)))

        cancel = CancelMyOrder(
            unit_of_work=DjangoUnitOfWork(),
            orders=DjangoOrderRepository(),
            inventory=DjangoInventory(),
            audit=build_audit_recorder(),
        )
        with pytest.raises(OrderNotFoundError):
            cancel.execute(CancelMyOrderCommand(owner=_owner(intruder), number=order.number.value))
        # The order is untouched and stock stays deducted.
        assert DjangoStockRepository().get_quantity("HB-250").value == 4
