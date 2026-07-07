"""Integration tests for the card-to-card endpoints (real stack).

Drive the full manual-transfer flow: a shopper initiates a card-to-card payment, reads the
per-channel destination card, submits their transfer reference, and staff confirm it (which
captures the payment and marks the order paid) or reject it (which fails it and frees the
order). Cover the authorization boundary (only staff with manage_orders confirm/reject),
owner-scoping/IDOR (a shopper cannot touch another's payment), and the conflict paths.
"""

from __future__ import annotations

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from tests.integration.payment.test_payment_endpoints import (
    _ORDERS_URL,
    _PAYMENTS_URL,
    _client,
    _initiate,
    _place_user_order,
    _seed_catalog,
    _user,
)
from tests.integration.payment.test_refund_endpoint import _staff

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_EXPECTED_CARD = "6037-9911-1234-5678"
_EXPECTED_HOLDER = "Polymart Store"
_TRANSFER = "TRK-778899"


def _instructions(client: APIClient, number: str):
    return client.get(f"{_PAYMENTS_URL}for-order/{number}/card-to-card/")


def _submit(client: APIClient, number: str, transfer: str = _TRANSFER):
    return client.post(
        f"{_PAYMENTS_URL}for-order/{number}/transfer-reference/",
        {"transfer_reference": transfer},
        format="json",
    )


def _confirm(client: APIClient, reference: str):
    return client.post(f"{_PAYMENTS_URL}{reference}/confirm/", format="json")


def _reject(client: APIClient, reference: str):
    return client.post(f"{_PAYMENTS_URL}{reference}/reject/", format="json")


def _start_card_to_card(client: APIClient, number: str) -> str:
    initiation = _initiate(client, number, method="card_to_card")
    assert initiation.status_code == 201, initiation.data
    return initiation.data["reference"]


class TestCardToCardHappyPath:
    def test_full_flow_buyer_submits_then_staff_confirms(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        reference = _start_card_to_card(shopper_client, number)

        # The buyer reads the channel's destination card to make the manual transfer.
        instructions = _instructions(shopper_client, number)
        assert instructions.status_code == 200
        assert instructions.data["card_number"] == _EXPECTED_CARD
        assert instructions.data["card_holder"] == _EXPECTED_HOLDER

        # The buyer reports the transfer reference; the payment is still pending.
        submitted = _submit(shopper_client, number)
        assert submitted.status_code == 200, submitted.data
        assert submitted.data["transfer_reference"] == _TRANSFER
        assert submitted.data["status"] == "pending"
        assert shopper_client.get(f"{_ORDERS_URL}{number}/").data["status"] == "pending"

        # Staff verify the transfer and confirm it: the payment captures, the order is paid.
        confirmed = _confirm(_client(_staff()), reference)
        assert confirmed.status_code == 200, confirmed.data
        assert confirmed.data["status"] == "captured"
        assert confirmed.data["transfer_reference"] == _TRANSFER
        assert shopper_client.get(f"{_ORDERS_URL}{number}/").data["status"] == "paid"

    def test_confirm_is_idempotent(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        reference = _start_card_to_card(shopper_client, number)
        _submit(shopper_client, number)
        staff_client = _client(_staff())

        first = _confirm(staff_client, reference)
        second = _confirm(staff_client, reference)

        assert first.status_code == 200
        assert second.status_code == 200  # a repeat is a no-op, not an error
        assert second.data["status"] == "captured"


class TestCardToCardReject:
    def test_staff_reject_fails_the_payment_and_frees_the_order(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        reference = _start_card_to_card(shopper_client, number)
        _submit(shopper_client, number)

        rejected = _reject(_client(_staff()), reference)

        assert rejected.status_code == 200, rejected.data
        assert rejected.data["status"] == "failed"
        # The order stays pending, and a fresh payment attempt is allowed (no active payment).
        assert shopper_client.get(f"{_ORDERS_URL}{number}/").data["status"] == "pending"
        retry = _initiate(shopper_client, number, method="card_to_card")
        assert retry.status_code == 201


class TestCardToCardAuthorization:
    def test_a_non_staff_user_cannot_confirm_or_reject(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        reference = _start_card_to_card(shopper_client, number)
        _submit(shopper_client, number)

        assert _confirm(shopper_client, reference).status_code == 403
        assert _reject(shopper_client, reference).status_code == 403
        # And the payment is untouched -- still pending.
        assert shopper_client.get(f"{_PAYMENTS_URL}{reference}/").data["status"] == "pending"

    def test_an_anonymous_request_cannot_confirm_or_reject(self) -> None:
        assert _confirm(APIClient(), "PAY-ABCDEF").status_code == 401
        assert _reject(APIClient(), "PAY-ABCDEF").status_code == 401


class TestCardToCardOwnerScoping:
    def test_a_shopper_cannot_submit_a_transfer_for_anothers_order(self) -> None:
        _seed_catalog()
        owner = _user("09120000001")
        owner_client, number = _place_user_order(owner, quantity=2)
        _start_card_to_card(owner_client, number)

        attacker_client = _client(_user("09120000002"))
        # The attacker cannot read the instructions for, or submit a transfer against, an
        # order that is not theirs -- indistinguishable from a nonexistent order (404).
        assert _instructions(attacker_client, number).status_code == 404
        assert _submit(attacker_client, number).status_code == 404


class TestCardToCardConflicts:
    def test_submitting_before_initiating_is_not_found(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        # No payment initiated yet -> no active payment to attach a reference to.
        assert _submit(shopper_client, number).status_code == 404

    def test_a_second_submission_is_refused(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        _start_card_to_card(shopper_client, number)

        assert _submit(shopper_client, number).status_code == 200
        assert _submit(shopper_client, number, transfer="TRK-OTHER").status_code == 409

    def test_confirming_without_a_submitted_transfer_is_refused(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        reference = _start_card_to_card(shopper_client, number)

        # No transfer reference submitted yet: staff have nothing to verify.
        assert _confirm(_client(_staff()), reference).status_code == 409

    def test_confirming_a_cod_payment_is_refused(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        cod = _initiate(shopper_client, number, method="cod")
        reference = cod.data["reference"]

        # A non-card-to-card payment cannot be confirmed through this path.
        assert _confirm(_client(_staff()), reference).status_code == 409

    def test_rejecting_a_cod_payment_is_refused(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        reference = _initiate(shopper_client, number, method="cod").data["reference"]

        # A non-card-to-card payment cannot be rejected through this path.
        assert _reject(_client(_staff()), reference).status_code == 409

    def test_a_malformed_order_number_is_not_found(self) -> None:
        _seed_catalog()
        shopper_client = _client(_user("09120000001"))
        # A structurally invalid order number can never match; surfaced as 404, not 400.
        assert _instructions(shopper_client, "!!bad!!").status_code == 404
        assert _submit(shopper_client, "!!bad!!").status_code == 404

    def test_a_missing_or_malformed_reference_is_not_found(self) -> None:
        staff_client = _client(_staff())
        assert _confirm(staff_client, "PAY-NOPE0001").status_code == 404
        assert _confirm(staff_client, "!!bad!!").status_code == 404
        assert _reject(staff_client, "PAY-NOPE0001").status_code == 404
        assert _reject(staff_client, "!!bad!!").status_code == 404


class TestCardToCardMisconfigured:
    @override_settings(PAYMENT_CARD_TO_CARD={})
    def test_instructions_when_no_card_is_configured_for_the_channel(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        _start_card_to_card(shopper_client, number)

        # The channel has no receiving card configured -- a server-side gap surfaced as 409.
        assert _instructions(shopper_client, number).status_code == 409

    @override_settings(PAYMENT_CARD_TO_CARD={"ir-main": {"number": "6037-0000-0000-0000"}})
    def test_instructions_when_the_card_config_is_incomplete(self) -> None:
        _seed_catalog()
        shopper = _user("09120000001")
        shopper_client, number = _place_user_order(shopper, quantity=2)
        _start_card_to_card(shopper_client, number)

        # A partial entry (no holder) is treated as not configured rather than shown blank.
        assert _instructions(shopper_client, number).status_code == 409
