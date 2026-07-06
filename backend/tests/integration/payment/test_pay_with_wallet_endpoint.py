"""Integration tests for pay-with-wallet through the payment endpoint (real stack).

Drive the full money loop: fund the shopper's wallet (pay an online order, staff refund it
to the wallet), then pay a *new* order from that balance. Assert the payment is captured, the
order is marked paid, and the wallet is debited by exactly the order total. Cover the refusals
(an uncovered balance, a guest with no wallet) and the double-pay guard.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from src.domain.cart.value_objects import CartQuantity
from src.domain.cart.value_objects import Sku as CartSku
from src.infrastructure.cart.repositories import DjangoCartRepository
from tests.integration.payment.test_payment_endpoints import (
    _ADDRESS_ID,
    _CHANNEL,
    _INLINE_ADDRESS,
    _ORDERS_URL,
    _client,
    _initiate,
    _place_user_order,
    _seed_catalog,
    _user,
)
from tests.integration.payment.test_refund_endpoint import _pay_online, _refund, _staff

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_WALLET_URL = "/api/v1/wallet/"
# One unit at 120000: the order total a wallet payment of the second order settles.
_UNIT_TOTAL = "120000.0000"
# Two units at 120000: the captured total of the first order, refunded to fund the wallet.
_FUNDING_TOTAL = "240000.0000"


def _fund_wallet(shopper) -> APIClient:
    """Pay an online order and have staff refund it, leaving the shopper's wallet funded."""
    shopper_client, number = _place_user_order(shopper, quantity=2)
    reference = _pay_online(shopper_client, number)
    assert _refund(_client(_staff()), reference).status_code == 200
    wallet = shopper_client.get(_WALLET_URL)
    assert wallet.data["balance"] == _FUNDING_TOTAL
    return shopper_client


def _place_second_order(shopper, client: APIClient, *, quantity: int = 1) -> str:
    """Add to the (now empty) cart and place a second order reusing the seeded address."""
    DjangoCartRepository().apply(
        f"u:{shopper.pk}",
        _CHANNEL,
        lambda cart: cart.add_item(CartSku("HB-250"), CartQuantity(quantity)),
    )
    placed = client.post(
        _ORDERS_URL, {"channel": _CHANNEL, "address_id": _ADDRESS_ID}, format="json"
    )
    assert placed.status_code == 201, placed.data
    return placed.data["number"]


class TestPayWithWallet:
    def test_pays_a_new_order_from_the_wallet_balance(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        client = _fund_wallet(shopper)
        number = _place_second_order(shopper, client, quantity=1)

        response = _initiate(client, number, method="wallet")

        assert response.status_code == 201, response.data
        assert response.data["method"] == "wallet"
        assert response.data["status"] == "captured"
        assert response.data["next_action"] == "none"
        # The order is paid, settled instantly and internally.
        assert client.get(f"{_ORDERS_URL}{number}/").data["status"] == "paid"

        # The wallet was debited by exactly the order total (240000 funded - 120000 spent).
        wallet = client.get(_WALLET_URL)
        assert wallet.data["balance"] == _UNIT_TOTAL
        debit = next(t for t in wallet.data["transactions"] if t["type"] == "debit")
        assert debit["amount"] == _UNIT_TOTAL
        assert debit["reason"] == "order_payment"
        assert debit["source_reference"] == response.data["reference"]

    def test_a_second_wallet_payment_for_the_same_order_is_refused(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        client = _fund_wallet(shopper)
        number = _place_second_order(shopper, client, quantity=1)

        assert _initiate(client, number, method="wallet").status_code == 201
        # The captured payment is active; a second attempt cannot double-debit.
        assert _initiate(client, number, method="wallet").status_code == 409

    def test_an_uncovered_balance_is_refused_and_debits_nothing(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        # No wallet funding: the balance (zero) cannot cover the order total.
        client, number = _place_user_order(shopper, quantity=2)

        response = _initiate(client, number, method="wallet")

        assert response.status_code == 409
        # The order stays payable and the wallet is still empty (nothing was written).
        assert client.get(f"{_ORDERS_URL}{number}/").data["status"] == "pending"
        wallet = client.get(_WALLET_URL)
        # A shopper who never received credit reads an empty wallet (zero, no ledger).
        assert wallet.data["balance"] == "0"
        assert wallet.data["transactions"] == []

    def test_a_guest_cannot_pay_with_a_wallet(self) -> None:
        _seed_catalog()
        guest = APIClient()
        guest.post(
            "/api/v1/cart/items/",
            {"channel": _CHANNEL, "sku": "HB-250", "quantity": 1},
            format="json",
        )
        placed = guest.post(
            _ORDERS_URL,
            {"channel": _CHANNEL, "shipping_address": _INLINE_ADDRESS},
            format="json",
        )
        assert placed.status_code == 201, placed.data
        number = placed.data["number"]

        response = _initiate(guest, number, method="wallet")

        assert response.status_code == 409  # a guest has no wallet to pay from
        assert guest.get(f"{_ORDERS_URL}{number}/").data["status"] == "pending"
