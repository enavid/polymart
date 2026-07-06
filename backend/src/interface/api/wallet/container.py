"""Composition root for the wallet slice.

The only place that wires concrete infrastructure adapters into the wallet use cases.
Views depend on these factories, never on infrastructure directly. ``CreditWallet`` is also
consumed by the payment refund bridge (wired in the payment container), so its factory lives
here alongside the read.
"""

from __future__ import annotations

from django.conf import settings

from src.application.wallet.use_cases import CreditWallet, DebitWallet, GetMyWallet
from src.infrastructure.wallet.clock import SystemClock
from src.infrastructure.wallet.repositories import DjangoUnitOfWork, DjangoWalletRepository
from src.interface.api.audit.container import build_audit_recorder


def build_credit_wallet() -> CreditWallet:
    return CreditWallet(
        unit_of_work=DjangoUnitOfWork(),
        wallets=DjangoWalletRepository(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
    )


def build_debit_wallet() -> DebitWallet:
    return DebitWallet(
        unit_of_work=DjangoUnitOfWork(),
        wallets=DjangoWalletRepository(),
        clock=SystemClock(),
        audit=build_audit_recorder(),
    )


def build_get_my_wallet() -> GetMyWallet:
    return GetMyWallet(
        wallets=DjangoWalletRepository(),
        default_currency=settings.WALLET_DEFAULT_CURRENCY,
    )
