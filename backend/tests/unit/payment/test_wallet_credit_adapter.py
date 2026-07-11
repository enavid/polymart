"""Unit tests for the wallet-credit adapter's exception translation (no DB, no framework).

The adapter bridges the payment ``WalletCredit`` port to the wallet ``CreditWallet`` use case.
Its one piece of logic worth covering in isolation is the seam guarantee: a wallet-domain
``WalletCurrencyMismatchError`` must be re-raised as the payment context's own
``RefundCurrencyMismatchError``, so no wallet exception leaks into the payment transport.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.domain.payment.exceptions import RefundCurrencyMismatchError
from src.domain.wallet.exceptions import WalletCurrencyMismatchError
from src.infrastructure.payment.wallet_credit import WalletCreditAdapter

_REFERENCE = "PAY-TEST01"


class _StubCreditWallet:
    """Stand-in for ``CreditWallet``; records the call or raises a preset error."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self._raises = raises
        self.calls: list[object] = []

    def execute(self, command: object) -> None:
        self.calls.append(command)
        if self._raises is not None:
            raise self._raises


def _credit(adapter: WalletCreditAdapter) -> None:
    adapter.credit(
        owner="u:7",
        amount=Decimal("240000"),
        currency="IRR",
        source_reference=_REFERENCE,
        reason="refund",
        actor="u:1",
    )


class TestWalletCreditAdapter:
    def test_delegates_a_successful_credit_to_the_use_case(self) -> None:
        stub = _StubCreditWallet()
        _credit(WalletCreditAdapter(stub))  # type: ignore[arg-type]
        assert len(stub.calls) == 1

    def test_translates_a_currency_mismatch_into_the_payment_error(self) -> None:
        stub = _StubCreditWallet(raises=WalletCurrencyMismatchError("IRR", "USD"))

        with pytest.raises(RefundCurrencyMismatchError) as exc_info:
            _credit(WalletCreditAdapter(stub))  # type: ignore[arg-type]

        # The payment-context error carries the payment reference, not the wallet detail.
        assert exc_info.value.reference == _REFERENCE
