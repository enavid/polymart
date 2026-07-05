"""Adapter implementing the payment context's ``WalletCredit`` port via the wallet context.

The refund use case (payment) needs to return value as store credit without depending on
the wallet domain. This adapter is the seam: it translates the narrow, primitive-typed port
call into the wallet's own ``CreditWallet`` use case. It runs inside the refund's
transaction (the use case's ``atomic()`` nests as a savepoint), so the payment refund and
the wallet credit commit together, and it inherits the wallet's idempotency by source
reference.
"""

from __future__ import annotations

from decimal import Decimal

from src.application.payment.ports import WalletCredit
from src.application.wallet.use_cases import CreditWallet, CreditWalletCommand


class WalletCreditAdapter(WalletCredit):
    """Bridge the payment ``WalletCredit`` port to the wallet ``CreditWallet`` use case."""

    def __init__(self, credit_wallet: CreditWallet) -> None:
        self._credit_wallet = credit_wallet

    def credit(
        self,
        *,
        owner: str,
        amount: Decimal,
        currency: str,
        source_reference: str,
        reason: str,
        actor: str,
    ) -> None:
        self._credit_wallet.execute(
            CreditWalletCommand(
                owner=owner,
                amount=amount,
                currency=currency,
                reason=reason,
                actor=actor,
                source_reference=source_reference,
            )
        )
