"""Integration tests for the wallet read endpoint (real stack).

The wallet is authenticated-only and owner-scoped: a user reads their own balance and
statement, an anonymous request is rejected, and a user never sees another's wallet. A user
with no wallet yet reads an empty one (zero balance) rather than a 404.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from rest_framework.test import APIClient

from src.application.wallet.use_cases import CreditWallet, CreditWalletCommand
from src.infrastructure.wallet.clock import SystemClock
from src.infrastructure.wallet.repositories import DjangoUnitOfWork, DjangoWalletRepository
from src.interface.api.audit.container import build_audit_recorder

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

_WALLET_URL = "/api/v1/wallet/"


def _user(phone: str) -> AbstractBaseUser:
    return get_user_model().objects.create_user(phone_number=phone, password="pw")


def _client(user: AbstractBaseUser) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _credit(owner: str, *, amount: str, source: str | None) -> None:
    CreditWallet(
        unit_of_work=DjangoUnitOfWork(),
        wallets=DjangoWalletRepository(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
    ).execute(
        CreditWalletCommand(
            owner=owner,
            amount=Decimal(amount),
            currency="IRR",
            reason="refund",
            actor="u:1",
            source_reference=source,
        )
    )


class TestWalletEndpoint:
    def test_an_untouched_user_reads_an_empty_wallet(self) -> None:
        user = _user("09120000001")

        response = _client(user).get(_WALLET_URL)

        assert response.status_code == 200
        assert response.data["balance"] == "0"
        assert response.data["currency"] == "IRR"
        assert response.data["transactions"] == []

    def test_a_user_reads_their_balance_and_statement(self) -> None:
        user = _user("09120000001")
        _credit(f"u:{user.pk}", amount="100.00", source="PAY-A")
        _credit(f"u:{user.pk}", amount="50.00", source="PAY-B")

        response = _client(user).get(_WALLET_URL)

        assert response.data["balance"] == "150.0000"
        assert len(response.data["transactions"]) == 2
        # Newest first.
        assert response.data["transactions"][0]["source_reference"] == "PAY-B"

    def test_an_anonymous_request_is_rejected(self) -> None:
        assert APIClient().get(_WALLET_URL).status_code == 401

    def test_a_user_never_sees_anothers_wallet(self) -> None:
        owner = _user("09120000001")
        _credit(f"u:{owner.pk}", amount="100.00", source="PAY-A")
        other = _user("09120000002")

        response = _client(other).get(_WALLET_URL)

        assert response.data["balance"] == "0"  # the other user's own (empty) wallet
        assert response.data["transactions"] == []
