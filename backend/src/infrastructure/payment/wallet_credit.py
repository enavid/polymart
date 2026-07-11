"""Adapter implementing the payment context's ``WalletCredit`` port via the wallet context.

The refund use case (payment) needs to return value as store credit without depending on
the wallet domain. This adapter is the seam: it translates the narrow, primitive-typed port
call into the wallet's own ``CreditWallet`` use case. It runs inside the refund's
transaction (the use case's ``atomic()`` nests as a savepoint), so the payment refund and
the wallet credit commit together, and it inherits the wallet's idempotency by source
reference.

It also translates the wallet's ``WalletCurrencyMismatchError`` into the payment context's own
``RefundCurrencyMismatchError``, so no wallet-domain exception crosses this seam -- the payment
transport maps only its own error types.
"""

from __future__ import annotations

from decimal import Decimal

from src.application.payment.ports import WalletCredit
from src.application.wallet.use_cases import CreditWallet, CreditWalletCommand
from src.domain.payment.exceptions import RefundCurrencyMismatchError
from src.domain.wallet.exceptions import WalletCurrencyMismatchError


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
        try:
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
        except WalletCurrencyMismatchError as exc:
            # Translate the wallet-domain error into the payment context's own type, so the
            # payment transport never has to know about wallet exceptions.
            raise RefundCurrencyMismatchError(source_reference) from exc
