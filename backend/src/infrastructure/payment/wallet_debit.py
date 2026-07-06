"""Adapter implementing the payment context's ``WalletDebit`` port via the wallet context.

Pay-with-wallet (payment) needs to spend the shopper's store credit without depending on the
wallet domain. This adapter is the seam: it translates the narrow, primitive-typed port call
into the wallet's own ``DebitWallet`` use case. It runs inside the payment's transaction (the
use case's ``atomic()`` nests as a savepoint), so the wallet debit and the payment's capture
commit together, and it inherits the wallet's idempotency by source reference.

It also translates the wallet's ``InsufficientWalletFundsError`` into the payment context's own
``InsufficientWalletBalanceError``, so no wallet-domain exception crosses this seam -- the
payment transport maps only its own error types.
"""

from __future__ import annotations

from decimal import Decimal

from src.application.payment.ports import WalletDebit
from src.application.wallet.use_cases import DebitWallet, DebitWalletCommand
from src.domain.payment.exceptions import InsufficientWalletBalanceError
from src.domain.wallet.exceptions import InsufficientWalletFundsError


class WalletDebitAdapter(WalletDebit):
    """Bridge the payment ``WalletDebit`` port to the wallet ``DebitWallet`` use case."""

    def __init__(self, debit_wallet: DebitWallet) -> None:
        self._debit_wallet = debit_wallet

    def debit(
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
            self._debit_wallet.execute(
                DebitWalletCommand(
                    owner=owner,
                    amount=amount,
                    currency=currency,
                    reason=reason,
                    actor=actor,
                    source_reference=source_reference,
                )
            )
        except InsufficientWalletFundsError as exc:
            # Translate the wallet-domain error into the payment context's own type, so the
            # payment transport never has to know about wallet exceptions.
            raise InsufficientWalletBalanceError(source_reference) from exc
