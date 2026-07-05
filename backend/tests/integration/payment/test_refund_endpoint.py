"""Integration tests for the staff refund-to-wallet endpoint (real stack).

Drive the full money flow: a shopper pays online (initiate -> callback -> capture -> order
paid), then staff refund the captured payment, which moves the payment to refunded and
credits the shopper's wallet with the exact captured amount. Cover idempotency (a repeated
refund never double-credits), the conflict paths (not captured, a guest owner), and the
authorization boundary (only staff with manage_orders).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser, Permission
from rest_framework.test import APIClient

from tests.integration.payment.test_payment_endpoints import (
    _CHANNEL,
    _INLINE_ADDRESS,
    _ORDERS_URL,
    _PAYMENTS_URL,
    _client,
    _initiate,
    _place_user_order,
    _seed_catalog,
    _user,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_WALLET_URL = "/api/v1/wallet/"
# Two units at 120000 each: the captured order total that a full refund returns.
_ORDER_TOTAL = "240000.0000"


def _staff() -> AbstractBaseUser:
    user = get_user_model().objects.create_user(
        phone_number="09120000009", password="pw", is_staff=True
    )
    perm = Permission.objects.get(content_type__app_label="order", codename="manage_orders")
    user.user_permissions.add(perm)
    return user


def _pay_online(client: APIClient, number: str) -> str:
    """Initiate an online payment and settle it via the mock callback; return the reference."""
    initiation = _initiate(client, number, method="online")
    assert initiation.status_code == 201, initiation.data
    reference = initiation.data["reference"]
    authority = initiation.data["redirect_url"].split("authority=")[1]
    callback = client.get(f"{_PAYMENTS_URL}callback/?Authority={authority}&Status=OK")
    assert callback.status_code == 302
    return reference


def _refund(client: APIClient, reference: str):
    return client.post(f"{_PAYMENTS_URL}{reference}/refund/", format="json")


class TestRefundToWallet:
    def test_staff_refund_moves_the_payment_to_refunded_and_credits_the_wallet(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        reference = _pay_online(shopper_client, number)
        assert shopper_client.get(f"{_ORDERS_URL}{number}/").data["status"] == "paid"

        response = _refund(_client(_staff()), reference)

        assert response.status_code == 200, response.data
        assert response.data["status"] == "refunded"
        # The shopper's wallet now holds the full captured amount as store credit.
        wallet = shopper_client.get(_WALLET_URL)
        assert wallet.data["balance"] == _ORDER_TOTAL
        assert wallet.data["currency"] == "IRR"
        assert len(wallet.data["transactions"]) == 1
        entry = wallet.data["transactions"][0]
        assert entry["type"] == "credit"
        assert entry["amount"] == _ORDER_TOTAL
        assert entry["reason"] == "refund"
        assert entry["source_reference"] == reference

    def test_refund_is_idempotent_and_never_double_credits(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        reference = _pay_online(shopper_client, number)
        staff_client = _client(_staff())

        first = _refund(staff_client, reference)
        second = _refund(staff_client, reference)

        assert first.status_code == 200
        assert second.status_code == 200  # a repeat is a no-op, not an error
        assert second.data["status"] == "refunded"
        wallet = shopper_client.get(_WALLET_URL)
        assert wallet.data["balance"] == _ORDER_TOTAL  # credited once
        assert len(wallet.data["transactions"]) == 1

    def test_a_pending_payment_cannot_be_refunded(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        pending = _initiate(shopper_client, number, method="cod")  # pending, not captured
        reference = pending.data["reference"]

        response = _refund(_client(_staff()), reference)

        assert response.status_code == 409

    def test_a_guest_payment_cannot_be_refunded_to_a_wallet(self) -> None:
        _seed_catalog()
        guest = APIClient()
        # A guest builds a cart, places an order, and pays online.

        cart_add = guest.post(
            "/api/v1/cart/items/",
            {"channel": _CHANNEL, "sku": "HB-250", "quantity": 1},
            format="json",
        )
        assert cart_add.status_code in (200, 201), cart_add.data
        placed = guest.post(
            _ORDERS_URL,
            {"channel": _CHANNEL, "shipping_address": _INLINE_ADDRESS},
            format="json",
        )
        assert placed.status_code == 201, placed.data
        number = placed.data["number"]
        reference = _pay_online(guest, number)

        response = _refund(_client(_staff()), reference)

        assert response.status_code == 409  # a guest has no wallet to receive credit

    def test_a_non_staff_user_cannot_refund(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        reference = _pay_online(shopper_client, number)

        # The shopper (no manage_orders) cannot refund their own payment.
        assert _refund(shopper_client, reference).status_code == 403

    def test_an_anonymous_request_cannot_refund(self) -> None:
        assert _refund(APIClient(), "PAY-ABCDEF").status_code == 401

    def test_a_missing_payment_is_not_found(self) -> None:
        assert _refund(_client(_staff()), "PAY-NOPE0001").status_code == 404

    def test_a_malformed_reference_is_not_found(self) -> None:
        # A structurally invalid reference can never match; surfaced as 404 (not 400), so the
        # shape of a valid reference is not probed.
        assert _refund(_client(_staff()), "!!bad!!").status_code == 404
