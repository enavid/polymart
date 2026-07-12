"""Integration tests for the Django order repository + adapters (real DB).

These prove the persistence mapping round-trips, that reads are owner-scoped, and that
the inventory adapter translates catalog stock errors into order-domain errors. The
end-to-end atomicity of checkout (deduct + create + clear + audit) is exercised through
the use case in ``test_place_order_integration.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from src.domain.catalog.entities import Product, ProductType, ProductVariant
from src.domain.catalog.value_objects import ProductCode, ProductTypeCode, StockQuantity
from src.domain.catalog.value_objects import Sku as CatalogSku
from src.domain.order.entities import Order, OrderLine
from src.domain.order.exceptions import (
    OrderNotFoundError,
    OutOfStockError,
)
from src.domain.order.value_objects import (
    ChannelRef,
    Money,
    OrderNumber,
    OrderQuantity,
    OrderStatus,
    ShippingAddress,
    Sku,
)
from src.infrastructure.catalog.repositories import (
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoStockRepository,
    DjangoVariantRepository,
)
from src.infrastructure.inventory.repositories import DjangoStockLevelRepository
from src.infrastructure.order.models import OrderLineModel, OrderModel
from src.infrastructure.order.repositories import (
    DjangoCartForCheckout,
    DjangoInventory,
    DjangoOrderRepository,
    DjangoPricingReader,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _available(sku: str) -> int:
    """Available-to-promise for a SKU across sources (on_hand - reserved)."""
    return DjangoStockLevelRepository().available_for_skus([sku]).get(sku, 0)


def _user(phone: str = "09120000001"):
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


def _owner(user: object) -> str:
    """The prefixed owner id the order context keys a signed-in user's orders by."""
    return f"u:{user.pk}"


def _seed_variant(sku: str, stock: int) -> None:
    """Create the minimal catalog rows so a variant has on-hand stock."""
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="C"))
    DjangoProductRepository().add(
        Product(code=ProductCode("house-blend"), name="H", product_type=ProductTypeCode("coffee"))
    )
    DjangoVariantRepository().add(
        ProductVariant(product=ProductCode("house-blend"), sku=CatalogSku(sku), name="v")
    )
    DjangoStockRepository().set_quantity(sku, StockQuantity(stock))


def _line(sku: str, qty: int, unit: str) -> OrderLine:
    unit_price = Money(amount=Decimal(unit), currency="IRR")
    quantity = OrderQuantity(qty)
    return OrderLine(
        sku=Sku(sku),
        quantity=quantity,
        unit_price=unit_price,
        line_total=unit_price.times(quantity),
    )


def _shipping_address() -> ShippingAddress:
    return ShippingAddress(
        recipient_name="Sara Ahmadi",
        phone_number="+989123456789",
        province="Tehran",
        city="Tehran",
        postal_code="1234567890",
        line1="Valiasr St, No. 1",
        line2=None,
    )


def _order(owner: str, number: str = "ORD-ABC123XYZ0") -> Order:
    lines = (_line("HB-250", 2, "120000.00"), _line("DR-250", 1, "150000.00"))
    total = Money.zero("IRR")
    for line in lines:
        total = total.add(line.line_total)
    return Order(
        number=OrderNumber(number),
        owner=owner,
        channel=ChannelRef("ir-main"),
        currency="IRR",
        lines=lines,
        total=total,
        status=OrderStatus.PENDING,
        placed_at=datetime(2026, 7, 2, tzinfo=UTC),
        shipping_address=_shipping_address(),
    )


class TestOrderRepository:
    def test_round_trips_an_order_with_its_lines(self) -> None:
        user = _user()
        repo = DjangoOrderRepository()

        saved = repo.add(_order(_owner(user)))
        reloaded = repo.get_for_owner(_owner(user), "ORD-ABC123XYZ0")

        assert reloaded.id == saved.id
        assert reloaded.total.amount == Decimal("390000.00")
        assert [line.sku.value for line in reloaded.lines] == ["HB-250", "DR-250"]
        assert reloaded.lines[0].unit_price.amount == Decimal("120000.00")
        assert reloaded.status is OrderStatus.PENDING
        # The captured shipping address round-trips through the DB losslessly.
        assert reloaded.shipping_address == _shipping_address()

    def test_reads_are_owner_scoped(self) -> None:
        owner = _user("09120000001")
        other = _user("09120000002")
        repo = DjangoOrderRepository()
        repo.add(_order(_owner(owner)))

        with pytest.raises(OrderNotFoundError):
            repo.get_for_owner(_owner(other), "ORD-ABC123XYZ0")

    def test_a_missing_order_raises_not_found(self) -> None:
        user = _user()
        with pytest.raises(OrderNotFoundError):
            DjangoOrderRepository().get_for_owner(_owner(user), "ORD-MISSING0000")

    def test_get_reads_any_order_by_number_not_owner_scoped(self) -> None:
        # The un-scoped read backs the pre-invoice (gated by manage_orders): it resolves
        # an order by number alone, regardless of who owns it.
        owner = _user("09120000001")
        repo = DjangoOrderRepository()
        repo.add(_order(_owner(owner)))

        found = repo.get("ORD-ABC123XYZ0")

        assert found.number.value == "ORD-ABC123XYZ0"
        assert found.owner == _owner(owner)
        with pytest.raises(OrderNotFoundError):
            repo.get("ORD-MISSING0000")

    def test_lists_newest_first_with_count(self) -> None:
        user = _user()
        repo = DjangoOrderRepository()
        repo.add(_order(_owner(user), "ORD-FIRST000000"))
        repo.add(_order(_owner(user), "ORD-SECOND00000"))

        rows, total = repo.list_for_owner(_owner(user), limit=10, offset=0)

        assert total == 2
        assert rows[0].number.value == "ORD-SECOND00000"  # newest first

    def test_set_status_persists_the_change(self) -> None:
        user = _user()
        repo = DjangoOrderRepository()
        saved = repo.add(_order(_owner(user)))

        updated = repo.set_status(saved, OrderStatus.CANCELLED)

        assert updated.status is OrderStatus.CANCELLED
        assert repo.get_for_owner(_owner(user), "ORD-ABC123XYZ0").status is OrderStatus.CANCELLED

    def test_round_trips_a_guest_order_by_token(self) -> None:
        # A guest order carries no user FK -- only the session token -- and reloads by it,
        # keyed by the same opaque owner string as a user's (``g:<token>``).
        repo = DjangoOrderRepository()
        owner = "g:guest-token-xyz"

        saved = repo.add(_order(owner))
        reloaded = repo.get_for_owner(owner, "ORD-ABC123XYZ0")

        assert reloaded.owner == owner
        assert reloaded.id == saved.id
        assert reloaded.total.amount == Decimal("390000.00")

    def test_a_guest_and_a_user_order_do_not_collide(self) -> None:
        # Same order number cannot exist twice, so distinct owners get distinct numbers;
        # each owner-kind resolves only its own row.
        repo = DjangoOrderRepository()
        user = _user()
        repo.add(_order(_owner(user), "ORD-USER000001"))
        repo.add(_order("g:guest-token-xyz", "ORD-GUEST00001"))

        with pytest.raises(OrderNotFoundError):
            repo.get_for_owner("g:guest-token-xyz", "ORD-USER000001")
        with pytest.raises(OrderNotFoundError):
            repo.get_for_owner(_owner(user), "ORD-GUEST00001")


class TestInventoryAdapter:
    def test_deduct_reserves_against_available_leaving_on_hand(self) -> None:
        # Placing an order reserves stock: the physical on-hand is untouched (fulfilment
        # settles it later), but available-to-promise drops by the reserved quantity.
        _seed_variant("HB-250", 5)

        DjangoInventory().deduct("HB-250", 3)

        assert DjangoStockRepository().get_quantity("HB-250").value == 5
        assert _available("HB-250") == 2

    def test_restock_releases_the_reservation(self) -> None:
        _seed_variant("HB-250", 5)
        DjangoInventory().deduct("HB-250", 3)

        DjangoInventory().restock("HB-250", 3)

        assert DjangoStockRepository().get_quantity("HB-250").value == 5
        assert _available("HB-250") == 5

    def test_deduct_beyond_available_raises_out_of_stock(self) -> None:
        _seed_variant("HB-250", 1)

        with pytest.raises(OutOfStockError) as exc:
            DjangoInventory().deduct("HB-250", 2)
        assert exc.value.available == 1

    def test_deduct_a_variant_with_no_stock_is_out_of_stock(self) -> None:
        # The inventory context is keyed by SKU, not the catalog variant: a SKU with no
        # stock level has zero available, which reads as out of stock (not a 404).
        with pytest.raises(OutOfStockError) as exc:
            DjangoInventory().deduct("NOPE-1", 1)
        assert exc.value.available == 0


class TestCartForCheckoutBridge:
    def test_clearing_an_owner_with_no_cart_is_a_no_op(self) -> None:
        # Checkout clears the cart inside its unit of work; an owner who never had a cart
        # in this channel must clear cleanly (no row to touch), not error.
        DjangoCartForCheckout().clear("u:404", "ir-main")

        assert DjangoCartForCheckout().line_items("u:404", "ir-main") == ()


class TestPricingReaderBridge:
    def test_an_unpriced_variant_reads_as_none(self) -> None:
        # A variant with no price row in the channel cannot be captured for an order, so
        # the reader returns None (the use case then refuses the line).
        assert DjangoPricingReader().price_of("NO-SUCH-SKU", "ir-main") is None


class TestModelRepr:
    def test_order_and_line_reprs_are_readable(self) -> None:
        # The admin/debug reprs identify a row at a glance; exercise them directly.
        user = _user()
        saved = DjangoOrderRepository().add(_order(_owner(user)))

        order_model = OrderModel.objects.get(id=saved.id)
        line_model = OrderLineModel.objects.filter(order=order_model).order_by("position").first()

        assert str(order_model) == "ORD-ABC123XYZ0"
        assert line_model is not None
        assert str(line_model) == f"{order_model.id}:{line_model.sku}:{line_model.quantity}"
