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
    VariantNotFoundError,
)
from src.domain.order.value_objects import (
    ChannelRef,
    Money,
    OrderNumber,
    OrderQuantity,
    OrderStatus,
    Sku,
)
from src.infrastructure.catalog.repositories import (
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoStockRepository,
    DjangoVariantRepository,
)
from src.infrastructure.order.repositories import (
    DjangoInventory,
    DjangoOrderRepository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _user(phone: str = "09120000001"):
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


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
    )


class TestOrderRepository:
    def test_round_trips_an_order_with_its_lines(self) -> None:
        user = _user()
        repo = DjangoOrderRepository()

        saved = repo.add(_order(str(user.pk)))
        reloaded = repo.get_for_owner(str(user.pk), "ORD-ABC123XYZ0")

        assert reloaded.id == saved.id
        assert reloaded.total.amount == Decimal("390000.00")
        assert [line.sku.value for line in reloaded.lines] == ["HB-250", "DR-250"]
        assert reloaded.lines[0].unit_price.amount == Decimal("120000.00")
        assert reloaded.status is OrderStatus.PENDING

    def test_reads_are_owner_scoped(self) -> None:
        owner = _user("09120000001")
        other = _user("09120000002")
        repo = DjangoOrderRepository()
        repo.add(_order(str(owner.pk)))

        with pytest.raises(OrderNotFoundError):
            repo.get_for_owner(str(other.pk), "ORD-ABC123XYZ0")

    def test_a_missing_order_raises_not_found(self) -> None:
        user = _user()
        with pytest.raises(OrderNotFoundError):
            DjangoOrderRepository().get_for_owner(str(user.pk), "ORD-MISSING0000")

    def test_lists_newest_first_with_count(self) -> None:
        user = _user()
        repo = DjangoOrderRepository()
        repo.add(_order(str(user.pk), "ORD-FIRST000000"))
        repo.add(_order(str(user.pk), "ORD-SECOND00000"))

        rows, total = repo.list_for_owner(str(user.pk), limit=10, offset=0)

        assert total == 2
        assert rows[0].number.value == "ORD-SECOND00000"  # newest first

    def test_set_status_persists_the_change(self) -> None:
        user = _user()
        repo = DjangoOrderRepository()
        saved = repo.add(_order(str(user.pk)))

        updated = repo.set_status(saved, OrderStatus.CANCELLED)

        assert updated.status is OrderStatus.CANCELLED
        assert repo.get_for_owner(str(user.pk), "ORD-ABC123XYZ0").status is OrderStatus.CANCELLED


class TestInventoryAdapter:
    def test_deduct_reduces_stock(self) -> None:
        _seed_variant("HB-250", 5)

        DjangoInventory().deduct("HB-250", 3)

        assert DjangoStockRepository().get_quantity("HB-250").value == 2

    def test_restock_returns_stock(self) -> None:
        _seed_variant("HB-250", 5)
        DjangoInventory().deduct("HB-250", 3)

        DjangoInventory().restock("HB-250", 3)

        assert DjangoStockRepository().get_quantity("HB-250").value == 5

    def test_deduct_beyond_stock_raises_out_of_stock(self) -> None:
        _seed_variant("HB-250", 1)

        with pytest.raises(OutOfStockError) as exc:
            DjangoInventory().deduct("HB-250", 2)
        assert exc.value.available == 1

    def test_deduct_unknown_variant_raises(self) -> None:
        with pytest.raises(VariantNotFoundError):
            DjangoInventory().deduct("NOPE-1", 1)
