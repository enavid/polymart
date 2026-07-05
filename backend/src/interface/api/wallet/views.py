"""Wallet endpoint (thin transport adapter).

A wallet always belongs to a registered user, so unlike the cart/order/payment endpoints
this route requires authentication: the owner is resolved from the authenticated user only
(``u:<pk>``), never from a client-supplied id, so one user can never read another's wallet.
"""

from __future__ import annotations

from typing import ClassVar

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from src.application.wallet.use_cases import WalletView
from src.interface.api.guest import user_owner
from src.interface.api.wallet.container import build_get_my_wallet
from src.interface.api.wallet.serializers import WalletSerializer


def _wallet_payload(view: WalletView) -> dict[str, object]:
    """Project the wallet read model to the response body (money as exact strings)."""
    return {
        "balance": str(view.balance.amount),
        "currency": view.balance.currency,
        "transactions": [
            {
                "type": txn.type.value,
                "amount": str(txn.amount.amount),
                "currency": txn.amount.currency,
                "reason": txn.reason,
                "balance_after": str(txn.balance_after.amount),
                "source_reference": txn.source_reference,
                "created_at": txn.created_at,
            }
            for txn in view.transactions
        ],
    }


class MyWalletView(APIView):
    """Read the authenticated user's own wallet: balance and recent ledger entries."""

    permission_classes: ClassVar = [IsAuthenticated]

    @extend_schema(operation_id="wallet_retrieve", responses={200: WalletSerializer})
    def get(self, request: Request) -> Response:
        view = build_get_my_wallet().execute(owner=user_owner(request.user.pk))
        return Response(_wallet_payload(view))
