"""Wallet use cases (interactors).

Each use case orchestrates the domain to fulfil one application intent: pure
orchestration, dependencies via constructor injection, business rules in the domain, side
effects (audit, structured logs) observable.

Crediting a wallet is idempotent by ``source_reference`` (a repeated refund never
double-credits), locks the wallet row so concurrent movements cannot lose an update,
creates the wallet lazily on first use, and records the money-relevant audit entry -- all
inside one ``UnitOfWork.atomic()``. Reads are owner-scoped, so one user can never see
another's wallet.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import structlog

from src.application.audit.ports import AuditRecorder
from src.application.shared.owner import safe_owner
from src.application.wallet.ports import Clock, UnitOfWork, WalletRepository
from src.domain.audit.entities import FieldChange
from src.domain.wallet.entities import Wallet, WalletTransaction
from src.domain.wallet.exceptions import InsufficientWalletFundsError
from src.domain.wallet.value_objects import Money

logger = structlog.get_logger(__name__)

_RESOURCE_WALLET = "wallet"
_ACTION_WALLET_CREDITED = "wallet.credited"
_ACTION_WALLET_DEBITED = "wallet.debited"
# The most recent ledger entries shown on the wallet statement.
_TRANSACTION_PAGE_LIMIT = 50


@dataclass(frozen=True)
class CreditWalletCommand:
    """Input for crediting a user's wallet with internal store credit.

    ``owner`` is the beneficiary's resolved id (``u:<pk>``). ``amount``/``currency`` are the
    exact captured value to add (a ``Decimal``, never a float). ``actor`` is who caused the
    credit (safe to audit -- a staff id for a refund). ``source_reference`` ties the credit
    to what caused it (a payment reference) and is the idempotency key.
    """

    owner: str
    amount: Decimal
    currency: str
    reason: str
    actor: str
    source_reference: str | None


class CreditWallet:
    """Add store credit to a user's wallet, idempotently and atomically.

    A movement already recorded for the same ``source_reference`` is returned unchanged (a
    repeated refund never double-credits). Otherwise the wallet row is locked (created lazily
    if absent), the domain applies the credit, the new balance and ledger entry are persisted
    together, and the credit is audited -- all in one transaction.
    """

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        wallets: WalletRepository,
        clock: Clock,
        audit: AuditRecorder,
    ) -> None:
        self._uow = unit_of_work
        self._wallets = wallets
        self._clock = clock
        self._audit = audit

    def execute(self, command: CreditWalletCommand) -> WalletTransaction:
        amount = Money(amount=command.amount, currency=command.currency)
        with self._uow.atomic():
            existing = self._find_existing(command)
            if existing is not None:
                logger.info(
                    "wallet_credit_ignored",
                    owner=safe_owner(command.owner),
                    source_reference=command.source_reference,
                    reason="already_recorded",
                )
                return existing

            wallet = self._wallets.get_for_update(command.owner)
            if wallet is None:
                wallet = self._wallets.create(
                    Wallet.empty(owner=command.owner, currency=command.currency)
                )
            balance_before = wallet.balance
            movement = wallet.credit(
                amount,
                reason=command.reason,
                source_reference=command.source_reference,
                at=self._clock.now(),
            )
            stored = self._wallets.save_movement(movement)
            self._audit.record(
                action=_ACTION_WALLET_CREDITED,
                resource_type=_RESOURCE_WALLET,
                resource_id=safe_owner(command.owner),
                actor=command.actor,
                changes=(
                    FieldChange(
                        field="balance",
                        before=str(balance_before.amount),
                        after=str(movement.wallet.balance.amount),
                    ),
                    FieldChange(field="amount", after=str(amount.amount)),
                    FieldChange(field="reason", after=command.reason),
                    FieldChange(field="source_reference", after=command.source_reference),
                ),
            )

        logger.info(
            "wallet_credited",
            owner=safe_owner(command.owner),
            reason=command.reason,
            source_reference=command.source_reference,
            currency=amount.currency,
        )
        return stored

    def _find_existing(self, command: CreditWalletCommand) -> WalletTransaction | None:
        if command.source_reference is None:
            return None
        return self._wallets.find_transaction_by_source(command.owner, command.source_reference)


@dataclass(frozen=True)
class DebitWalletCommand:
    """Input for spending a user's wallet balance (paying with store credit).

    ``owner`` is the payer's resolved id (``u:<pk>``). ``amount``/``currency`` are the exact
    order total to remove (a ``Decimal``, never a float). ``actor`` is who caused the debit
    (the payer themselves for a pay-with-wallet). ``source_reference`` ties the debit to what
    caused it (the wallet payment's reference) and is the idempotency key.
    """

    owner: str
    amount: Decimal
    currency: str
    reason: str
    actor: str
    source_reference: str | None


class DebitWallet:
    """Remove store credit from a user's wallet, idempotently and atomically.

    A movement already recorded for the same ``source_reference`` is returned unchanged (a
    repeated debit never double-spends). Otherwise the wallet row is locked; a wallet that
    does not exist (or whose balance cannot cover the amount) is refused with
    ``InsufficientWalletFundsError`` and nothing is written; on success the domain applies the
    debit, the new balance and ledger entry are persisted together, and the debit is audited
    -- all in one transaction.
    """

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        wallets: WalletRepository,
        clock: Clock,
        audit: AuditRecorder,
    ) -> None:
        self._uow = unit_of_work
        self._wallets = wallets
        self._clock = clock
        self._audit = audit

    def execute(self, command: DebitWalletCommand) -> WalletTransaction:
        amount = Money(amount=command.amount, currency=command.currency)
        with self._uow.atomic():
            existing = self._find_existing(command)
            if existing is not None:
                logger.info(
                    "wallet_debit_ignored",
                    owner=safe_owner(command.owner),
                    source_reference=command.source_reference,
                    reason="already_recorded",
                )
                return existing

            wallet = self._wallets.get_for_update(command.owner)
            if wallet is None:
                # No wallet yet means no balance to spend; refuse rather than create one so a
                # pay-with-wallet against an empty account fails cleanly (nothing is written).
                raise InsufficientWalletFundsError(balance="0", amount=str(amount.amount))
            balance_before = wallet.balance
            movement = wallet.debit(
                amount,
                reason=command.reason,
                source_reference=command.source_reference,
                at=self._clock.now(),
            )
            stored = self._wallets.save_movement(movement)
            self._audit.record(
                action=_ACTION_WALLET_DEBITED,
                resource_type=_RESOURCE_WALLET,
                resource_id=safe_owner(command.owner),
                actor=command.actor,
                changes=(
                    FieldChange(
                        field="balance",
                        before=str(balance_before.amount),
                        after=str(movement.wallet.balance.amount),
                    ),
                    FieldChange(field="amount", after=str(amount.amount)),
                    FieldChange(field="reason", after=command.reason),
                    FieldChange(field="source_reference", after=command.source_reference),
                ),
            )

        logger.info(
            "wallet_debited",
            owner=safe_owner(command.owner),
            reason=command.reason,
            source_reference=command.source_reference,
            currency=amount.currency,
        )
        return stored

    def _find_existing(self, command: DebitWalletCommand) -> WalletTransaction | None:
        if command.source_reference is None:
            return None
        return self._wallets.find_transaction_by_source(command.owner, command.source_reference)


@dataclass(frozen=True)
class WalletView:
    """A wallet's balance plus its recent statement, for the read endpoint."""

    balance: Money
    transactions: Sequence[WalletTransaction]


class GetMyWallet:
    """Read the authenticated user's own wallet: balance and recent ledger entries.

    A user who has never received credit has no wallet row yet; rather than 404, that reads
    as an empty wallet (a zero balance in the platform's default currency) with no entries,
    so the storefront can always render the page.
    """

    def __init__(self, *, wallets: WalletRepository, default_currency: str) -> None:
        self._wallets = wallets
        self._default_currency = default_currency

    def execute(self, *, owner: str) -> WalletView:
        wallet = self._wallets.get_for_owner(owner)
        if wallet is None:
            zero = Money(amount=Decimal("0"), currency=self._default_currency)
            return WalletView(balance=zero, transactions=())
        transactions = self._wallets.list_transactions(owner, limit=_TRANSACTION_PAGE_LIMIT)
        return WalletView(balance=wallet.balance, transactions=transactions)
