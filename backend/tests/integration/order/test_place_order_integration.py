"""End-to-end integration tests for checkout against the real stack (DB + adapters).

This is the money/inventory-critical path, so it is tested with the real Django
adapters wired together (no fakes): the Unit of Work, the locked stock repository, the
order repository, the cart bridge, and the durable audit trail. Placing an order
*reserves* stock (available-to-promise drops; physical on-hand is untouched until
fulfilment); cancelling releases the reservation. The decisive test is that an oversell
on one line rolls back the reservation already made on an earlier line -- the
multi-aggregate atomicity guarantee.
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
from src.infrastructure.inventory.repositories import DjangoStockLevelRepository
from src.infrastructure.order.clock import SystemClock
from src.infrastructure.order.repositories import (
    ConfiguredShippingRateReader,
    ConfiguredTaxCalculator,
    DjangoAddressReader,
    DjangoCartForCheckout,
    DjangoChannelReader,
    DjangoInventory,
    DjangoOrderRepository,
    DjangoPricingReader,
    DjangoUnitOfWork,
    DjangoVariantWeightReader,
)
from src.interface.api.audit.container import build_audit_recorder
from src.interface.api.events.container import build_event_publisher
from tests.integration.order.factories import seed_address

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CHANNEL = "ir-main"
_ADDRESS_ID = "ADDR-SHIP000001"
# The default channel's flat-rate methods come from settings.SHIPPING_METHODS (see
# config/settings/test.py): "standard" costs this much, added to the goods subtotal.
_STANDARD_SHIPPING = Decimal("50000")


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


def _available(sku: str) -> int:
    """Available-to-promise for a SKU (on_hand - reserved); the buyable count."""
    return DjangoStockLevelRepository().available_for_skus([sku]).get(sku, 0)


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
        weights=DjangoVariantWeightReader(),
        channels=DjangoChannelReader(),
        addresses=DjangoAddressReader(),
        shipping=ConfiguredShippingRateReader(),
        tax=ConfiguredTaxCalculator(),
        inventory=DjangoInventory(),
        orders=DjangoOrderRepository(),
        numbers=numbers or _FixedNumbers(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
        events=build_event_publisher(),
    )


def _checkout_command(owner: str) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        owner=owner, channel=_CHANNEL, shipping_method="standard", address_id=_ADDRESS_ID
    )


class TestCheckoutWeightRates:
    def test_captures_the_weight_bracket_cost_from_the_order_weight(self, settings) -> None:  # type: ignore[no-untyped-def]
        # A weight-priced method: the captured shipping cost is the bracket the order's total
        # weight falls into, resolved server-side from the catalog weights (not the client).
        from src.infrastructure.catalog.models import ProductVariantModel

        settings.SHIPPING_METHODS = {
            _CHANNEL: [
                {
                    "code": "table",
                    "name": "Weight table",
                    "currency": "IRR",
                    "min_days": 2,
                    "max_days": 4,
                    "weight_brackets": [
                        {"up_to_grams": 1000, "price": "30000"},
                        {"up_to_grams": None, "price": "90000"},
                    ],
                }
            ]
        }
        _seed_catalog()
        # HB-250 weighs 600g; ordering 2 = 1200g, which lands in the overflow bracket (90000).
        ProductVariantModel.objects.filter(sku="HB-250").update(weight_grams=600)
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        _add_to_cart(owner, "HB-250", 2)

        order = _place_order().execute(
            PlaceOrderCommand(
                owner=owner, channel=_CHANNEL, shipping_method="table", address_id=_ADDRESS_ID
            )
        )

        assert order.shipping is not None
        assert order.shipping.cost.amount == Decimal("90000")
        # Goods 240000 + shipping 90000 = 330000 grand total (untaxed test channel).
        assert order.total.amount == Decimal("330000")

    def test_a_light_order_gets_the_lighter_bracket(self, settings) -> None:  # type: ignore[no-untyped-def]
        from src.infrastructure.catalog.models import ProductVariantModel

        settings.SHIPPING_METHODS = {
            _CHANNEL: [
                {
                    "code": "table",
                    "name": "Weight table",
                    "currency": "IRR",
                    "min_days": 2,
                    "max_days": 4,
                    "weight_brackets": [
                        {"up_to_grams": 1000, "price": "30000"},
                        {"up_to_grams": None, "price": "90000"},
                    ],
                }
            ]
        }
        _seed_catalog()
        ProductVariantModel.objects.filter(sku="HB-250").update(weight_grams=400)
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        _add_to_cart(owner, "HB-250", 1)  # 400g -> the <=1000 bracket (30000)

        order = _place_order().execute(
            PlaceOrderCommand(
                owner=owner, channel=_CHANNEL, shipping_method="table", address_id=_ADDRESS_ID
            )
        )

        assert order.shipping is not None
        assert order.shipping.cost.amount == Decimal("30000")


class TestCheckoutHappyPath:
    def test_places_an_order_reserves_stock_clears_cart_and_audits(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        _add_to_cart(owner, "HB-250", 2)
        _add_to_cart(owner, "DR-250", 1)

        order = _place_order().execute(_checkout_command(owner))

        # Order persisted with the captured grand total (goods 390000 + shipping 50000).
        assert order.items_subtotal.amount == Decimal("390000.00")
        assert order.total.amount == Decimal("390000.00") + _STANDARD_SHIPPING
        assert order.status is OrderStatus.PENDING
        # The captured shipping selection persists and reloads (round-trip through the ORM).
        reloaded = DjangoOrderRepository().get_for_owner(owner, order.number.value)
        assert reloaded.id == order.id
        assert reloaded.shipping is not None
        assert reloaded.shipping.method_code == "standard"
        assert reloaded.shipping.cost.amount == _STANDARD_SHIPPING
        assert reloaded.total.amount == order.total.amount
        # The shipping address was captured from the shopper's address book.
        assert order.shipping_address.recipient_name == "Sara Ahmadi"
        # Stock reserved for both lines: available drops, physical on-hand untouched.
        assert _available("HB-250") == 3
        assert _available("DR-250") == 0
        assert DjangoStockRepository().get_quantity("HB-250").value == 5
        assert DjangoStockRepository().get_quantity("DR-250").value == 1
        # Cart cleared.
        assert DjangoCartForCheckout().line_items(owner, _CHANNEL) == ()
        # Placement audited durably.
        assert AuditLogModel.objects.filter(
            action="order.placed", resource_id=order.number.value
        ).exists()


class TestCheckoutTax:
    def test_captures_and_reloads_tax_on_subtotal_plus_shipping(self, settings) -> None:  # type: ignore[no-untyped-def]
        # A taxed channel: tax applies to goods + shipping, is captured onto the order, and
        # survives the round-trip through the ORM (the reloaded order carries the same tax).
        settings.TAX_RATES = {"ir-main": "9"}
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        _add_to_cart(owner, "HB-250", 2)

        order = _place_order().execute(_checkout_command(owner))

        # Goods 240000 + shipping 50000 = 290000 base; 9% tax = 26100; grand total 316100.
        assert order.tax is not None
        assert order.tax.rate == Decimal("9")
        assert order.tax.amount.amount == Decimal("26100")
        assert order.total.amount == Decimal("316100")
        reloaded = DjangoOrderRepository().get_for_owner(owner, order.number.value)
        assert reloaded.tax is not None
        assert reloaded.tax.rate == Decimal("9")
        assert reloaded.tax.amount.amount == Decimal("26100")
        assert reloaded.total.amount == Decimal("316100")

    def test_an_untaxed_channel_captures_no_tax(self, settings) -> None:  # type: ignore[no-untyped-def]
        settings.TAX_RATES = {}
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000002", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        _add_to_cart(owner, "HB-250", 1)

        order = _place_order().execute(_checkout_command(owner))

        assert order.tax is None
        assert DjangoOrderRepository().get_for_owner(owner, order.number.value).tax is None


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
                shipping_method="standard",
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
        assert order.total.amount == Decimal("240000.00") + _STANDARD_SHIPPING
        assert order.shipping is not None and order.shipping.method_code == "standard"
        assert order.shipping_address.recipient_name == "Guest Buyer"
        assert DjangoOrderRepository().get_for_owner(owner, order.number.value).id == order.id
        assert _available("HB-250") == 3
        assert DjangoCartForCheckout().line_items(owner, _CHANNEL) == ()


class TestCheckoutShippingRejection:
    def test_an_unknown_shipping_method_is_refused_and_places_nothing(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        _add_to_cart(owner, "HB-250", 1)

        from src.domain.order.exceptions import UnknownShippingMethodError

        with pytest.raises(UnknownShippingMethodError):
            _place_order().execute(
                PlaceOrderCommand(
                    owner=owner, channel=_CHANNEL, shipping_method="drone", address_id=_ADDRESS_ID
                )
            )
        # Refused before the transaction: no order, nothing reserved, cart intact.
        assert DjangoOrderRepository().list_for_owner(owner, limit=10, offset=0) == ((), 0)
        assert _available("HB-250") == 5
        assert len(DjangoCartForCheckout().line_items(owner, _CHANNEL)) == 1


class TestCheckoutAtomicity:
    def test_an_oversell_rolls_back_the_whole_checkout(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        # First line reserves fine; the second oversells DR-250 (only 1 in stock).
        _add_to_cart(owner, "HB-250", 2)
        _add_to_cart(owner, "DR-250", 5)

        with pytest.raises(OutOfStockError):
            _place_order().execute(_checkout_command(owner))

        # Nothing committed: no order, the earlier reservation reverted, cart intact.
        assert DjangoOrderRepository().list_for_owner(owner, limit=10, offset=0) == ((), 0)
        assert _available("HB-250") == 5
        assert _available("DR-250") == 1
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


class TestCheckoutBackorder:
    def test_a_backorderable_variant_places_past_available_stock(self) -> None:
        # DR-250 has 1 in stock but is backorderable: ordering 3 places the order and
        # tracks the 2-unit shortfall as backorder (physical on-hand untouched).
        from src.infrastructure.inventory.repositories import DjangoStockPolicyRepository

        _seed_catalog()
        DjangoStockPolicyRepository().set_policy(
            "DR-250", backorderable=True, low_stock_threshold=0
        )
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        _add_to_cart(owner, "DR-250", 3)

        order = _place_order().execute(_checkout_command(owner))

        assert order.status is OrderStatus.PENDING
        # All physical stock is reserved and the overflow is backordered; available is 0.
        assert _available("DR-250") == 0
        assert DjangoStockPolicyRepository().get("DR-250").backordered.value == 2


class TestCancelIntegration:
    def test_cancel_releases_the_reservation_and_is_audited(self) -> None:
        _seed_catalog()
        user = get_user_model().objects.create_user(phone_number="09120000001", password="pw")
        owner = _owner(user)
        seed_address(user.pk)
        _add_to_cart(owner, "HB-250", 2)
        order = _place_order().execute(_checkout_command(owner))
        assert _available("HB-250") == 3

        cancel = CancelMyOrder(
            unit_of_work=DjangoUnitOfWork(),
            orders=DjangoOrderRepository(),
            inventory=DjangoInventory(),
            audit=build_audit_recorder(),
        )
        result = cancel.execute(CancelMyOrderCommand(owner=owner, number=order.number.value))

        assert result.status is OrderStatus.CANCELLED
        assert _available("HB-250") == 5  # reservation released
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
        # The order is untouched and the reservation stays held.
        assert _available("HB-250") == 4
