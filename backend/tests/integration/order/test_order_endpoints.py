"""Integration tests for the order HTTP endpoints (real stack).

Cover both a signed-in user's checkout (saved address) and a guest's (inline address),
the owner-scoping that makes IDOR impossible for either, the money/stock conflict paths
(empty cart, oversell, unpurchasable line) as 409s, order history paging, and
cancel/restock.
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
_CART_ITEMS_URL = "/api/v1/cart/items/"
_ADDRESS_ID = "ADDR-SHIP000001"

# A guest's one-off inline shipping address (Iranian mobile + 10-digit postal), the shape
# the checkout form submits when there is no address book.
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
    # The cart context keys a user's cart as ``u:<pk>`` (guest carts use ``g:<token>``);
    # the order checkout still reads it by the bare pk, so seeding here mirrors what the
    # cart endpoints store for a signed-in shopper.
    DjangoCartRepository().apply(
        f"u:{owner_pk}", _CHANNEL, lambda cart: cart.add_item(CartSku(sku), CartQuantity(quantity))
    )


def _checkout(client: APIClient, *, address_id: str = _ADDRESS_ID, channel: str = _CHANNEL):
    """POST the checkout body (channel + saved address id)."""
    return client.post(_ORDERS_URL, {"channel": channel, "address_id": address_id}, format="json")


def _guest_add_to_cart(client: APIClient, sku: str, quantity: int):
    """Add a line as a guest -- the first write mints the guest session cookie, which the
    test client then carries on every later request (so the guest is remembered)."""
    return client.post(
        _CART_ITEMS_URL,
        {"channel": _CHANNEL, "sku": sku, "quantity": quantity},
        format="json",
    )


def _guest_checkout(client: APIClient, *, address=None, channel: str = _CHANNEL):
    """POST the checkout body a guest submits (channel + inline shipping address)."""
    return client.post(
        _ORDERS_URL,
        {"channel": channel, "shipping_address": address or _INLINE_ADDRESS},
        format="json",
    )


class TestGuestCheckout:
    """A guest (no account) builds a cart and checks out with an inline shipping address,
    remembered only by their HttpOnly session cookie."""

    def test_a_guest_places_an_order_with_an_inline_address(self) -> None:
        _seed_catalog()
        client = APIClient()
        assert _guest_add_to_cart(client, "HB-250", 2).status_code == 200

        response = _guest_checkout(client)

        assert response.status_code == 201
        assert response.data["status"] == "pending"
        assert response.data["total"] == "240000.0000"
        assert response.data["shipping_address"]["recipient_name"] == "Guest Buyer"
        assert response.data["shipping_address"]["city"] == "Isfahan"
        # Stock was captured for the guest's order exactly as for a user's.
        assert DjangoStockRepository().get_quantity("HB-250").value == 3

    def test_a_guest_can_read_and_list_only_their_own_order(self) -> None:
        _seed_catalog()
        client = APIClient()
        _guest_add_to_cart(client, "HB-250", 1)
        number = _guest_checkout(client).data["number"]

        # The same cookie resolves the guest's own order and history.
        assert client.get(f"{_ORDERS_URL}{number}/").status_code == 200
        assert client.get(_ORDERS_URL).data["count"] == 1

    def test_another_guest_cannot_see_the_order(self) -> None:
        # A fresh client carries no cookie -> a different (throwaway) guest identity, so
        # the order number leaks nothing even if guessed/replayed (IDOR).
        _seed_catalog()
        buyer = APIClient()
        _guest_add_to_cart(buyer, "HB-250", 1)
        number = _guest_checkout(buyer).data["number"]

        other = APIClient()
        assert other.get(f"{_ORDERS_URL}{number}/").status_code == 404
        assert other.get(_ORDERS_URL).data["count"] == 0

    def test_a_guest_cancels_their_pending_order_and_stock_is_restored(self) -> None:
        _seed_catalog()
        client = APIClient()
        _guest_add_to_cart(client, "HB-250", 2)
        number = _guest_checkout(client).data["number"]
        assert DjangoStockRepository().get_quantity("HB-250").value == 3

        response = client.post(f"{_ORDERS_URL}{number}/cancel/")

        assert response.status_code == 200
        assert response.data["status"] == "cancelled"
        assert DjangoStockRepository().get_quantity("HB-250").value == 5

    def test_a_cookieless_guest_with_an_empty_cart_is_a_409(self) -> None:
        # No cart write happened, so there is no cookie and no cart -> checkout conflicts.
        _seed_catalog()
        assert _guest_checkout(APIClient()).status_code == 409

    def test_supplying_both_address_id_and_inline_address_is_a_400(self) -> None:
        _seed_catalog()
        client = APIClient()
        _guest_add_to_cart(client, "HB-250", 1)

        response = client.post(
            _ORDERS_URL,
            {"channel": _CHANNEL, "address_id": _ADDRESS_ID, "shipping_address": _INLINE_ADDRESS},
            format="json",
        )
        assert response.status_code == 400

    def test_a_malformed_inline_phone_is_a_400(self) -> None:
        _seed_catalog()
        client = APIClient()
        _guest_add_to_cart(client, "HB-250", 1)

        response = _guest_checkout(client, address={**_INLINE_ADDRESS, "phone_number": "12345"})
        assert response.status_code == 400

    def test_a_guest_cannot_check_out_against_a_saved_address_id(self) -> None:
        # A guest has no address book, so a saved-address id resolves to nothing for them
        # (exactly like an unknown one) -- they must supply an inline address instead.
        _seed_catalog()
        client = APIClient()
        _guest_add_to_cart(client, "HB-250", 1)

        response = _checkout(client, address_id=_ADDRESS_ID)
        assert response.status_code == 400


class TestPlaceOrder:
    def test_places_an_order_and_returns_201(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        seed_address(user.pk)
        _add_to_cart(user.pk, "HB-250", 2)

        response = _checkout(_client(user))

        assert response.status_code == 201
        assert response.data["status"] == "pending"
        # Money round-trips through the DB at the stored 4-dp precision (as the
        # storefront/cart already expose), so the exact Decimal survives as a string.
        assert response.data["total"] == "240000.0000"
        assert response.data["number"].startswith("ORD-")
        assert response.data["items"][0]["unit_price"] == "120000.0000"
        # The shipping address was captured from the shopper's address book.
        assert response.data["shipping_address"]["recipient_name"] == "Sara Ahmadi"
        assert response.data["shipping_address"]["city"] == "Tehran"

    def test_a_missing_address_id_field_is_a_400(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        _add_to_cart(user.pk, "HB-250", 1)

        response = _client(user).post(_ORDERS_URL, {"channel": _CHANNEL}, format="json")

        assert response.status_code == 400

    def test_an_unknown_address_is_a_400(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        _add_to_cart(user.pk, "HB-250", 1)

        response = _checkout(_client(user), address_id="ADDR-DOESNOTEX")

        assert response.status_code == 400

    def test_cannot_checkout_with_another_users_address(self) -> None:
        # An address id belonging to another shopper must not be usable at checkout,
        # and resolves to the same 400 as a nonexistent one (no existence leak / IDOR).
        _seed_catalog()
        owner = _user("09120000001")
        intruder = _user("09120000002")
        owner_address = seed_address(owner.pk, address_id="ADDR-OWNER00001")
        _add_to_cart(intruder.pk, "HB-250", 1)

        response = _checkout(_client(intruder), address_id=owner_address)

        assert response.status_code == 400

    def test_an_empty_cart_is_a_409(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        seed_address(user.pk)

        response = _checkout(_client(user))

        assert response.status_code == 409

    def test_an_oversell_is_a_409(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        seed_address(user.pk)
        _add_to_cart(user.pk, "DR-250", 5)  # only 1 in stock

        response = _checkout(_client(user))

        assert response.status_code == 409
        # Stock untouched by the failed checkout.
        assert DjangoStockRepository().get_quantity("DR-250").value == 1

    def test_an_unknown_channel_is_a_400(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        seed_address(user.pk)
        _add_to_cart(user.pk, "HB-250", 1)

        response = _checkout(_client(user), channel="ghost")

        assert response.status_code == 400


class TestOrderHistory:
    def _place(self, user: AbstractBaseUser) -> str:
        response = _checkout(_client(user))
        assert response.status_code == 201
        return response.data["number"]

    def test_lists_only_the_callers_orders(self) -> None:
        _seed_catalog()
        alice = _user("09120000001")
        bob = _user("09120000002")
        seed_address(alice.pk)
        _add_to_cart(alice.pk, "HB-250", 1)
        self._place(alice)

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
        seed_address(user.pk)
        _add_to_cart(user.pk, "HB-250", 1)
        client = _client(user)
        number = _checkout(client).data["number"]

        response = client.get(f"{_ORDERS_URL}{number}/")

        assert response.status_code == 200
        assert response.data["number"] == number
        # The captured shipping address is projected on the detail read too.
        assert response.data["shipping_address"]["postal_code"] == "1234567890"

    def test_another_user_gets_404_not_the_order(self) -> None:
        _seed_catalog()
        owner = _user("09120000001")
        intruder = _user("09120000002")
        seed_address(owner.pk)
        _add_to_cart(owner.pk, "HB-250", 1)
        number = _checkout(_client(owner)).data["number"]

        # Guessing/replaying the number as another user must not reveal the order (IDOR).
        response = _client(intruder).get(f"{_ORDERS_URL}{number}/")
        assert response.status_code == 404

    def test_a_malformed_number_is_a_404(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        assert _client(user).get(f"{_ORDERS_URL}not-a-number!/").status_code == 404


class TestCancel:
    def _place(self, user: AbstractBaseUser) -> str:
        return _checkout(_client(user)).data["number"]

    def test_owner_cancels_a_pending_order_and_stock_is_restored(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        seed_address(user.pk)
        _add_to_cart(user.pk, "HB-250", 2)
        client = _client(user)
        number = self._place(user)
        assert DjangoStockRepository().get_quantity("HB-250").value == 3

        response = client.post(f"{_ORDERS_URL}{number}/cancel/")

        assert response.status_code == 200
        assert response.data["status"] == "cancelled"
        assert DjangoStockRepository().get_quantity("HB-250").value == 5

    def test_cancelling_twice_is_a_409(self) -> None:
        _seed_catalog()
        user = _user("09120000001")
        seed_address(user.pk)
        _add_to_cart(user.pk, "HB-250", 1)
        client = _client(user)
        number = self._place(user)
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
        seed_address(owner.pk)
        _add_to_cart(owner.pk, "HB-250", 1)
        number = self._place(owner)

        response = _client(intruder).post(f"{_ORDERS_URL}{number}/cancel/")
        assert response.status_code == 404
        # Owner's stock deduction stands.
        assert DjangoStockRepository().get_quantity("HB-250").value == 4


_MANUAL_URL = "/api/v1/orders/manual/"


def _staff_with_order_perm(phone: str = "09120000009") -> AbstractBaseUser:
    """A staff user granted the global manage_orders permission (the order_admin capability)."""
    from django.contrib.auth.models import Permission

    user = get_user_model().objects.create_user(phone_number=phone, password="pw", is_staff=True)
    perm = Permission.objects.get(content_type__app_label="order", codename="manage_orders")
    user.user_permissions.add(perm)
    return user


def _manual_body(items=None, *, channel: str = _CHANNEL, address=None) -> dict:
    return {
        "channel": channel,
        "items": items if items is not None else [{"sku": "HB-250", "quantity": 2}],
        "shipping_address": address or _INLINE_ADDRESS,
    }


class TestManualOrder:
    """Staff with manage_orders create a manual order (a pre-invoice) from explicit lines."""

    def test_staff_creates_a_manual_order_and_stock_is_deducted(self) -> None:
        _seed_catalog()
        staff = _staff_with_order_perm()
        client = _client(staff)

        response = client.post(
            _MANUAL_URL,
            _manual_body([{"sku": "HB-250", "quantity": 2}, {"sku": "DR-250", "quantity": 1}]),
            format="json",
        )

        assert response.status_code == 201
        assert response.data["status"] == "pending"
        assert response.data["total"] == "390000.0000"
        assert response.data["shipping_address"]["recipient_name"] == "Guest Buyer"
        # Stock captured exactly as a checkout would.
        assert DjangoStockRepository().get_quantity("HB-250").value == 3
        assert DjangoStockRepository().get_quantity("DR-250").value == 0
        # The manual order is owned by the creating staff, who can read it back.
        number = response.data["number"]
        assert client.get(f"{_ORDERS_URL}{number}/").status_code == 200

    def test_a_user_without_the_permission_is_forbidden(self) -> None:
        _seed_catalog()
        client = _client(_user("09120000001"))

        assert client.post(_MANUAL_URL, _manual_body(), format="json").status_code == 403
        # Nothing was created / no stock moved.
        assert DjangoStockRepository().get_quantity("HB-250").value == 5

    def test_an_anonymous_request_is_unauthorized(self) -> None:
        # Unauthenticated (no cookie) -> 401; an authenticated user lacking the perm -> 403.
        _seed_catalog()
        assert APIClient().post(_MANUAL_URL, _manual_body(), format="json").status_code == 401

    def test_a_duplicate_sku_is_rejected(self) -> None:
        _seed_catalog()
        client = _client(_staff_with_order_perm())

        response = client.post(
            _MANUAL_URL,
            _manual_body([{"sku": "HB-250", "quantity": 1}, {"sku": "HB-250", "quantity": 2}]),
            format="json",
        )

        assert response.status_code == 400

    def test_no_items_is_rejected(self) -> None:
        _seed_catalog()
        client = _client(_staff_with_order_perm())

        assert client.post(_MANUAL_URL, _manual_body([]), format="json").status_code == 400

    def test_an_oversell_is_a_conflict_and_writes_nothing(self) -> None:
        _seed_catalog()  # DR-250 stock is 1
        client = _client(_staff_with_order_perm())

        response = client.post(
            _MANUAL_URL, _manual_body([{"sku": "DR-250", "quantity": 2}]), format="json"
        )

        assert response.status_code == 409
        assert DjangoStockRepository().get_quantity("DR-250").value == 1

    def test_an_unknown_channel_is_a_400(self) -> None:
        _seed_catalog()
        client = _client(_staff_with_order_perm())

        response = client.post(_MANUAL_URL, _manual_body(channel="nope"), format="json")

        assert response.status_code == 400

    def test_a_malformed_inline_phone_is_a_400(self) -> None:
        _seed_catalog()
        client = _client(_staff_with_order_perm())
        bad = {**_INLINE_ADDRESS, "phone_number": "12345"}

        response = client.post(_MANUAL_URL, _manual_body(address=bad), format="json")

        assert response.status_code == 400


class TestPreInvoice:
    """Staff issue a printable pre-invoice for any order (gated by manage_orders)."""

    def test_staff_reads_the_pre_invoice_of_a_manual_order(self) -> None:
        _seed_catalog()
        client = _client(_staff_with_order_perm())
        number = client.post(_MANUAL_URL, _manual_body(), format="json").data["number"]

        response = client.get(f"{_ORDERS_URL}{number}/pre-invoice/")

        assert response.status_code == 200
        assert response.data["document_type"] == "pre_invoice"
        assert response.data["tax"] is None
        assert response.data["grand_total"] == "240000.0000"
        assert response.data["items"][0]["sku"] == "HB-250"

    def test_staff_can_pre_invoice_any_order_including_a_guest_order(self) -> None:
        # The pre-invoice is not owner-scoped: a staff member prints a proforma for a
        # shopper's order they did not place (authorized by the permission, not the owner).
        _seed_catalog()
        guest = APIClient()
        _guest_add_to_cart(guest, "HB-250", 1)
        number = _guest_checkout(guest).data["number"]

        staff = _client(_staff_with_order_perm())
        response = staff.get(f"{_ORDERS_URL}{number}/pre-invoice/")

        assert response.status_code == 200
        assert response.data["grand_total"] == "120000.0000"

    def test_an_unknown_number_is_a_404(self) -> None:
        _seed_catalog()
        client = _client(_staff_with_order_perm())

        assert client.get(f"{_ORDERS_URL}ORD-MISSING0000/pre-invoice/").status_code == 404

    def test_a_malformed_number_is_a_404(self) -> None:
        # Too short to be a valid order number -> surfaced as 404, never a 400 that would
        # let the shape of a real number be probed.
        _seed_catalog()
        client = _client(_staff_with_order_perm())

        assert client.get(f"{_ORDERS_URL}AB/pre-invoice/").status_code == 404

    def test_without_the_permission_it_is_forbidden(self) -> None:
        _seed_catalog()
        staff = _client(_staff_with_order_perm())
        number = staff.post(_MANUAL_URL, _manual_body(), format="json").data["number"]

        plain = _client(_user("09120000001"))
        assert plain.get(f"{_ORDERS_URL}{number}/pre-invoice/").status_code == 403
