"""Integration tests for the order HTTP endpoints (real stack).

Cover the secure-by-default posture (auth required), checkout (place → 201), the
owner-scoping that makes IDOR impossible, the money/stock conflict paths (empty cart,
oversell, unpurchasable line) as 409s, order history paging, and cancel/restock.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient

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
from src.infrastructure.cart.repositories import DjangoCartRepository
from src.infrastructure.catalog.repositories import (
    DjangoProductRepository,
    DjangoProductTypeRepository,
    DjangoStockRepository,
    DjangoVariantPriceRepository,
    DjangoVariantRepository,
)
from src.infrastructure.channel.repositories import DjangoChannelRepository

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CHANNEL = "ir-main"
_ORDERS_URL = "/api/v1/orders/"


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


def _user(phone: str) -> AbstractBaseUser:
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


def _client(user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _add_to_cart(owner_pk: int, sku: str, quantity: int) -> None:
    DjangoCartRepository().apply(
        str(owner_pk), _CHANNEL, lambda cart: cart.add_item(CartSku(sku), CartQuantity(quantity))
    )


class TestAuthorization:
    def test_anonymous_cannot_list_orders(self) -> None:
        assert APIClient().get(_ORDERS_URL).status_code == 401

    def test_anonymous_cannot_place_an_order(self) -> None:
        response = APIClient().post(_ORDERS_URL, {"channel": _CHANNEL}, format="json")
        assert response.status_code == 401


class TestPlaceOrder:
    def test_places_an_order_and_returns_201(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        _add_to_cart(user.pk, "HB-250", 2)

        response = _client(user).post(_ORDERS_URL, {"channel": _CHANNEL}, format="json")

        assert response.status_code == 201
        assert response.data["status"] == "pending"
        # Money round-trips through the DB at the stored 4-dp precision (as the
        # storefront/cart already expose), so the exact Decimal survives as a string.
        assert response.data["total"] == "240000.0000"
        assert response.data["number"].startswith("ORD-")
        assert response.data["items"][0]["unit_price"] == "120000.0000"

    def test_an_empty_cart_is_a_409(self) -> None:
        _seed_catalog()
        user = _user("09120000001")

        response = _client(user).post(_ORDERS_URL, {"channel": _CHANNEL}, format="json")

        assert response.status_code == 409

    def test_an_oversell_is_a_409(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        _add_to_cart(user.pk, "DR-250", 5)  # only 1 in stock

        response = _client(user).post(_ORDERS_URL, {"channel": _CHANNEL}, format="json")

        assert response.status_code == 409
        # Stock untouched by the failed checkout.
        assert DjangoStockRepository().get_quantity("DR-250").value == 1

    def test_an_unknown_channel_is_a_400(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        _add_to_cart(user.pk, "HB-250", 1)

        response = _client(user).post(_ORDERS_URL, {"channel": "ghost"}, format="json")

        assert response.status_code == 400


class TestOrderHistory:
    def _place(self, client: APIClient) -> str:
        response = client.post(_ORDERS_URL, {"channel": _CHANNEL}, format="json")
        assert response.status_code == 201
        return response.data["number"]

    def test_lists_only_the_callers_orders(self) -> None:
        _seed_catalog()
        alice = _user("09120000001")
        bob = _user("09120000002")
        _add_to_cart(alice.pk, "HB-250", 1)
        self._place(_client(alice))

        # Bob has no orders even though Alice placed one.
        bob_list = _client(bob).get(_ORDERS_URL)
        assert bob_list.data["count"] == 0

    def test_out_of_range_limit_is_a_400(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        assert _client(user).get(_ORDERS_URL, {"limit": 1000}).status_code == 400


class TestOrderDetailIdor:
    def test_owner_can_read_their_order(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        _add_to_cart(user.pk, "HB-250", 1)
        client = _client(user)
        number = client.post(_ORDERS_URL, {"channel": _CHANNEL}, format="json").data["number"]

        response = client.get(f"{_ORDERS_URL}{number}/")

        assert response.status_code == 200
        assert response.data["number"] == number

    def test_another_user_gets_404_not_the_order(self) -> None:
        _seed_catalog()
        owner = _user("09120000001")
        intruder = _user("09120000002")
        _add_to_cart(owner.pk, "HB-250", 1)
        number = (
            _client(owner).post(_ORDERS_URL, {"channel": _CHANNEL}, format="json").data["number"]
        )

        # Guessing/replaying the number as another user must not reveal the order (IDOR).
        response = _client(intruder).get(f"{_ORDERS_URL}{number}/")
        assert response.status_code == 404

    def test_a_malformed_number_is_a_404(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        assert _client(user).get(f"{_ORDERS_URL}not-a-number!/").status_code == 404


class TestCancel:
    def _place(self, client: APIClient) -> str:
        return client.post(_ORDERS_URL, {"channel": _CHANNEL}, format="json").data["number"]

    def test_owner_cancels_a_pending_order_and_stock_is_restored(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        _add_to_cart(user.pk, "HB-250", 2)
        client = _client(user)
        number = self._place(client)
        assert DjangoStockRepository().get_quantity("HB-250").value == 3

        response = client.post(f"{_ORDERS_URL}{number}/cancel/")

        assert response.status_code == 200
        assert response.data["status"] == "cancelled"
        assert DjangoStockRepository().get_quantity("HB-250").value == 5

    def test_cancelling_twice_is_a_409(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        _add_to_cart(user.pk, "HB-250", 1)
        client = _client(user)
        number = self._place(client)
        assert client.post(f"{_ORDERS_URL}{number}/cancel/").status_code == 200

        # The order is now cancelled; a repeat cancel is a conflict, and does not
        # restock a second time.
        assert client.post(f"{_ORDERS_URL}{number}/cancel/").status_code == 409
        assert DjangoStockRepository().get_quantity("HB-250").value == 5

    def test_cancelling_a_malformed_number_is_a_404(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        assert _client(user).post(f"{_ORDERS_URL}not-a-number!/cancel/").status_code == 404

    def test_another_user_cannot_cancel(self) -> None:
        _seed_catalog()
        owner = _user("09120000001")
        intruder = _user("09120000002")
        _add_to_cart(owner.pk, "HB-250", 1)
        number = self._place(_client(owner))

        response = _client(intruder).post(f"{_ORDERS_URL}{number}/cancel/")
        assert response.status_code == 404
        # Owner's stock deduction stands.
        assert DjangoStockRepository().get_quantity("HB-250").value == 4
