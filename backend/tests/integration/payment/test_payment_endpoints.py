"""Integration tests for the payment HTTP endpoints (real stack).

Cover a signed-in user's and a guest's COD initiation end to end (place an order, then
pay), the owner-scoping that makes IDOR impossible for either, the conflict paths
(unsupported method, double initiation, a non-pending order) and the reads. The amount is
always the order's captured total (never client-supplied), verified against the order.
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
from tests.integration.order.factories import seed_address

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_CHANNEL = "ir-main"
_ORDERS_URL = "/api/v1/orders/"
_PAYMENTS_URL = "/api/v1/payments/"
_CART_ITEMS_URL = "/api/v1/cart/items/"
_ADDRESS_ID = "ADDR-SHIP000001"

_INLINE_ADDRESS = {
    "recipient_name": "Guest Buyer",
    "phone_number": "09121112233",
    "province": "Isfahan",
    "city": "Isfahan",
    "postal_code": "8134567890",
    "line1": "Chaharbagh St, No. 9",
}


def _seed_catalog() -> None:
    DjangoChannelRepository().add(
        Channel(slug=ChannelSlug(_CHANNEL), name="Iran Main", currency=Currency("IRR"))
    )
    DjangoProductTypeRepository().add(ProductType(code=ProductTypeCode("coffee"), name="Coffee"))
    DjangoProductRepository().add(
        Product(code=ProductCode("house-blend"), name="H", product_type=ProductTypeCode("coffee"))
    )
    DjangoVariantRepository().add(
        ProductVariant(product=ProductCode("house-blend"), sku=CatalogSku("HB-250"), name="v")
    )
    DjangoVariantPriceRepository().replace(
        "HB-250",
        (
            ChannelPrice(
                channel=_CHANNEL, money=CatalogMoney(amount=Decimal("120000.00"), currency="IRR")
            ),
        ),
    )
    DjangoStockRepository().set_quantity("HB-250", StockQuantity(10))


def _user(phone: str) -> AbstractBaseUser:
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


def _client(user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _place_user_order(user: AbstractBaseUser, *, quantity: int = 2) -> tuple[APIClient, str]:
    """Seed a cart for the user, place an order, and return the client + order number."""
    seed_address(user.pk, address_id=_ADDRESS_ID)
    DjangoCartRepository().apply(
        f"u:{user.pk}",
        _CHANNEL,
        lambda cart: cart.add_item(CartSku("HB-250"), CartQuantity(quantity)),
    )
    client = _client(user)
    placed = client.post(
        _ORDERS_URL,
        {"channel": _CHANNEL, "shipping_method": "free", "address_id": _ADDRESS_ID},
        format="json",
    )
    assert placed.status_code == 201, placed.data
    return client, placed.data["number"]


def _initiate(client: APIClient, order_number: str, *, method: str = "cod"):
    return client.post(
        _PAYMENTS_URL, {"order_number": order_number, "method": method}, format="json"
    )


class TestUserCodPayment:
    def test_initiates_a_pending_cod_payment_for_the_order_total(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user, quantity=2)

        response = _initiate(client, number)

        assert response.status_code == 201, response.data
        assert response.data["status"] == "pending"
        assert response.data["method"] == "cod"
        # The amount is the order's captured total (2 x 120000), never client-supplied.
        assert response.data["amount"] == "240000.0000"
        assert response.data["currency"] == "IRR"
        assert response.data["order_number"] == number
        assert response.data["next_action"] == "none"
        assert response.data["redirect_url"] is None
        assert response.data["reference"].startswith("PAY-")

    def test_reads_the_payment_by_reference_and_by_order(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user)
        reference = _initiate(client, number).data["reference"]

        by_ref = client.get(f"{_PAYMENTS_URL}{reference}/")
        assert by_ref.status_code == 200
        assert by_ref.data["reference"] == reference

        by_order = client.get(f"{_PAYMENTS_URL}for-order/{number}/")
        assert by_order.status_code == 200
        assert by_order.data["reference"] == reference

    def test_double_initiation_is_rejected(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user)
        assert _initiate(client, number).status_code == 201

        second = _initiate(client, number)
        assert second.status_code == 409

    def test_card_to_card_initiates_a_pending_payment(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user)

        # card_to_card is a supported method: it starts a pending payment with no automatic
        # next action (the buyer transfers out of band and staff confirm it later).
        response = _initiate(client, number, method="card_to_card")
        assert response.status_code == 201
        body = response.json()
        assert body["method"] == "card_to_card"
        assert body["status"] == "pending"
        assert body["next_action"] == "none"
        assert body["transfer_reference"] is None

    def test_an_unknown_method_is_rejected_by_the_serializer(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user)

        response = _initiate(client, number, method="bitcoin")
        assert response.status_code == 400

    def test_a_cancelled_order_is_not_payable(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user)
        assert client.post(f"{_ORDERS_URL}{number}/cancel/").status_code == 200

        response = _initiate(client, number)
        assert response.status_code == 409

    def test_initiating_for_an_unknown_order_is_not_found(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client = _client(user)

        response = _initiate(client, "ORD-DOESNOTEXIST0")
        assert response.status_code == 404


class TestPaymentIdor:
    def test_a_shopper_cannot_initiate_payment_for_anothers_order(self) -> None:
        _seed_catalog()
        owner = _user("09120000001")
        _, number = _place_user_order(owner)

        attacker = _client(_user("09120000002"))
        # The order is not the attacker's, so it resolves to "not found" (no leak).
        assert _initiate(attacker, number).status_code == 404

    def test_a_shopper_cannot_read_anothers_payment(self) -> None:
        _seed_catalog()
        owner = _user("09120000001")
        owner_client, number = _place_user_order(owner)
        reference = _initiate(owner_client, number).data["reference"]

        attacker = _client(_user("09120000002"))
        assert attacker.get(f"{_PAYMENTS_URL}{reference}/").status_code == 404
        assert attacker.get(f"{_PAYMENTS_URL}for-order/{number}/").status_code == 404


class TestGuestCodPayment:
    def test_a_guest_pays_cod_end_to_end(self) -> None:
        _seed_catalog()
        client = APIClient()
        # First cart write mints the guest cookie, carried on every later request.
        assert (
            client.post(
                _CART_ITEMS_URL,
                {"channel": _CHANNEL, "sku": "HB-250", "quantity": 1},
                format="json",
            ).status_code
            == 200
        )
        number = client.post(
            _ORDERS_URL,
            {"channel": _CHANNEL, "shipping_method": "free", "shipping_address": _INLINE_ADDRESS},
            format="json",
        ).data["number"]

        response = _initiate(client, number)

        assert response.status_code == 201
        assert response.data["amount"] == "120000.0000"
        assert response.data["method"] == "cod"
        # The guest can read their own payment with the same cookie.
        assert client.get(f"{_PAYMENTS_URL}for-order/{number}/").status_code == 200

    def test_a_fresh_client_cannot_read_a_guests_payment(self) -> None:
        _seed_catalog()
        client = APIClient()
        client.post(
            _CART_ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 1}, format="json"
        )
        number = client.post(
            _ORDERS_URL,
            {"channel": _CHANNEL, "shipping_method": "free", "shipping_address": _INLINE_ADDRESS},
            format="json",
        ).data["number"]
        reference = _initiate(client, number).data["reference"]

        # A different client (no guest cookie) cannot see the guest's payment.
        stranger = APIClient()
        assert stranger.get(f"{_PAYMENTS_URL}{reference}/").status_code == 404


class TestPaymentReads:
    def test_payment_for_an_order_without_one_is_not_found(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user)

        # No payment initiated yet.
        assert client.get(f"{_PAYMENTS_URL}for-order/{number}/").status_code == 404

    def test_a_malformed_reference_is_not_found(self) -> None:
        _seed_catalog()
        client = _client(_user("09120000001"))
        assert client.get(f"{_PAYMENTS_URL}not-a-valid-ref!!/").status_code == 404

    def test_a_malformed_order_number_for_order_is_not_found(self) -> None:
        _seed_catalog()
        client = _client(_user("09120000001"))
        # A malformed order number can never match; surfaced as 404, not a 400.
        assert client.get(f"{_PAYMENTS_URL}for-order/bad!!/").status_code == 404


class TestOnlinePayment:
    """The full online flow via the mock gateway: initiate -> redirect -> callback ->
    capture -> order paid, plus idempotency, failure, and spoofing."""

    def _initiate_online(self, client: APIClient, number: str) -> str:
        response = _initiate(client, number, method="online")
        assert response.status_code == 201, response.data
        assert response.data["status"] == "pending"
        assert response.data["next_action"] == "redirect"
        assert "/payments/mock-gateway/" in response.data["redirect_url"]
        # The mock authority is derived from the payment reference.
        return f"MOCK-{response.data['reference']}"

    def _callback(self, client: APIClient, authority: str, status_value: str):
        return client.get(f"{_PAYMENTS_URL}callback/?Authority={authority}&Status={status_value}")

    def test_successful_callback_captures_and_pays_the_order(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user)
        authority = self._initiate_online(client, number)

        # The order is not paid until the callback settles it.
        assert client.get(f"{_ORDERS_URL}{number}/").data["status"] == "pending"

        response = self._callback(client, authority, "OK")
        assert response.status_code == 302
        assert f"/orders/{number}" in response["Location"]

        # Eager Celery: the capture ran, so the payment is captured and the order paid.
        assert client.get(f"{_PAYMENTS_URL}for-order/{number}/").data["status"] == "captured"
        assert client.get(f"{_ORDERS_URL}{number}/").data["status"] == "paid"

    def test_callback_is_idempotent(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user)
        authority = self._initiate_online(client, number)

        assert self._callback(client, authority, "OK").status_code == 302
        # A duplicate callback must not change anything (no double capture / double pay).
        assert self._callback(client, authority, "OK").status_code == 302
        assert client.get(f"{_PAYMENTS_URL}for-order/{number}/").data["status"] == "captured"
        assert client.get(f"{_ORDERS_URL}{number}/").data["status"] == "paid"

    def test_a_cancelled_callback_fails_the_payment_and_leaves_the_order_pending(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user)
        authority = self._initiate_online(client, number)

        assert self._callback(client, authority, "NOK").status_code == 302
        assert client.get(f"{_PAYMENTS_URL}for-order/{number}/").data["status"] == "failed"
        assert client.get(f"{_ORDERS_URL}{number}/").data["status"] == "pending"

    def test_a_failed_attempt_frees_the_order_for_a_retry(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        client, number = _place_user_order(user)
        authority = self._initiate_online(client, number)
        self._callback(client, authority, "NOK")  # first attempt fails

        # The failed payment no longer holds the order, so a fresh online attempt succeeds.
        retry_authority = self._initiate_online(client, number)
        assert self._callback(client, retry_authority, "OK").status_code == 302
        assert client.get(f"{_ORDERS_URL}{number}/").data["status"] == "paid"

    def test_an_unknown_authority_is_not_found(self) -> None:
        _seed_catalog()
        client = _client(_user("09120000001"))
        assert self._callback(client, "MOCK-NOPE", "OK").status_code == 404

    def test_a_missing_authority_is_a_bad_request(self) -> None:
        _seed_catalog()
        client = _client(_user("09120000001"))
        assert client.get(f"{_PAYMENTS_URL}callback/?Status=OK").status_code == 400

    def test_the_mock_gateway_page_renders_pay_and_cancel(self) -> None:
        _seed_catalog()
        client = APIClient()
        response = client.get(f"{_PAYMENTS_URL}mock-gateway/?authority=MOCK-ABC")
        assert response.status_code == 200
        assert b"mock_pay" in response.content
        assert b"mock_cancel" in response.content
        assert b"Status=OK" in response.content
        assert b"Status=NOK" in response.content

    def test_the_mock_gateway_page_is_inert_when_not_in_mock_mode(self) -> None:
        # In production (real gateway wired) the dev mock page must not be served.
        from django.test import override_settings

        with override_settings(PAYMENT_ONLINE_MOCK=False):
            response = APIClient().get(f"{_PAYMENTS_URL}mock-gateway/?authority=MOCK-ABC")
        assert response.status_code == 404

    def test_a_guest_pays_online_end_to_end(self) -> None:
        _seed_catalog()
        client = APIClient()
        client.post(
            _CART_ITEMS_URL, {"channel": _CHANNEL, "sku": "HB-250", "quantity": 1}, format="json"
        )
        number = client.post(
            _ORDERS_URL,
            {"channel": _CHANNEL, "shipping_method": "free", "shipping_address": _INLINE_ADDRESS},
            format="json",
        ).data["number"]
        authority = self._initiate_online(client, number)

        assert self._callback(client, authority, "OK").status_code == 302
        assert client.get(f"{_ORDERS_URL}{number}/").data["status"] == "paid"
