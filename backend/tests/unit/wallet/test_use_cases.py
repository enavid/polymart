"""Unit tests for the wallet use cases against fakes (no DB, no framework).

These exercise the orchestration: idempotency by source reference, lazy wallet creation,
the row-locked credit, audit recording, atomic rollback, and the owner-scoped read with an
empty-wallet fallback. The fakes stand in for the Django adapters wired at the composition
root.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from structlog.testing import capture_logs

from src.application.audit.ports import AuditRecorder
from src.application.wallet.ports import Clock, UnitOfWork, WalletRepository
from src.application.wallet.use_cases import (
    CreditWallet,
    CreditWalletCommand,
    DebitWallet,
    DebitWalletCommand,
    GetMyWallet,
)
from src.domain.audit.entities import FieldChange
from src.domain.wallet.entities import Wallet, WalletMovement, WalletTransaction
from src.domain.wallet.exceptions import (
    InsufficientWalletFundsError,
    WalletCurrencyMismatchError,
)
from src.domain.wallet.value_objects import Money, TransactionType

_OWNER = "u:7"
_AT = datetime(2026, 7, 5, 12, 0, tzinfo=UTC)


def _money(amount: str, currency: str = "IRR") -> Money:
    return Money(amount=Decimal(amount), currency=currency)


# --- Fakes ---------------------------------------------------------------


class FakeUnitOfWork(UnitOfWork):
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    @contextmanager
    def atomic(self) -> Iterator[None]:
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise
        self.committed = True


class FakeClock(Clock):
    def now(self) -> datetime:
        return _AT


class FakeWallets(WalletRepository):
    def __init__(self) -> None:
        self._wallets: dict[str, Wallet] = {}
        self._transactions: dict[str, list[WalletTransaction]] = {}
        self._next_wallet_id = 1
        self._next_txn_id = 1
        self.locked: list[str] = []

    def seed(self, wallet: Wallet) -> Wallet:
        stored = Wallet(owner=wallet.owner, balance=wallet.balance, id=self._next_wallet_id)
        self._next_wallet_id += 1
        self._wallets[wallet.owner] = stored
        return stored

    def get_for_owner(self, owner: str) -> Wallet | None:
        return self._wallets.get(owner)

    def get_for_update(self, owner: str) -> Wallet | None:
        self.locked.append(owner)
        return self._wallets.get(owner)

    def create(self, wallet: Wallet) -> Wallet:
        return self.seed(wallet)

    def save_movement(self, movement: WalletMovement) -> WalletTransaction:
        self._wallets[movement.wallet.owner] = movement.wallet
        stored = WalletTransaction(
            type=movement.transaction.type,
            amount=movement.transaction.amount,
            reason=movement.transaction.reason,
            balance_after=movement.transaction.balance_after,
            created_at=movement.transaction.created_at,
            source_reference=movement.transaction.source_reference,
            id=self._next_txn_id,
        )
        self._next_txn_id += 1
        self._transactions.setdefault(movement.wallet.owner, []).insert(0, stored)
        return stored

    def find_transaction_by_source(
        self, owner: str, source_reference: str
    ) -> WalletTransaction | None:
        for txn in self._transactions.get(owner, []):
            if txn.source_reference == source_reference:
                return txn
        return None

    def list_transactions(self, owner: str, *, limit: int) -> Sequence[WalletTransaction]:
        return tuple(self._transactions.get(owner, [])[:limit])


class RecordingAudit(AuditRecorder):
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str | None = None,
        changes: tuple[FieldChange, ...] = (),
    ) -> None:
        self.records.append(
            {
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "actor": actor,
                "changes": tuple(changes),
            }
        )


def _build_credit(
    *, wallets: FakeWallets | None = None, uow: FakeUnitOfWork | None = None
) -> tuple[CreditWallet, FakeWallets, FakeUnitOfWork, RecordingAudit]:
    wallets = wallets or FakeWallets()
    uow = uow or FakeUnitOfWork()
    audit = RecordingAudit()
    use_case = CreditWallet(unit_of_work=uow, wallets=wallets, clock=FakeClock(), audit=audit)
    return use_case, wallets, uow, audit


def _credit_command(
    *, amount: str = "150.00", source_reference: str | None = "PAY-ABC"
) -> CreditWalletCommand:
    return CreditWalletCommand(
        owner=_OWNER,
        amount=Decimal(amount),
        currency="IRR",
        reason="refund",
        actor="u:1",
        source_reference=source_reference,
    )


# --- CreditWallet --------------------------------------------------------


class TestCreditWallet:
    def test_creates_the_wallet_lazily_and_credits_it(self) -> None:
        use_case, wallets, uow, _audit = _build_credit()

        txn = use_case.execute(_credit_command())

        assert txn.type == TransactionType.CREDIT
        assert txn.amount == _money("150.00")
        assert txn.balance_after == _money("150.00")
        assert wallets.get_for_owner(_OWNER).balance == _money("150.00")
        assert uow.committed is True
        assert wallets.locked == [_OWNER]  # the wallet row was locked

    def test_credits_an_existing_wallet(self) -> None:
        wallets = FakeWallets()
        wallets.seed(
            Wallet.empty(owner=_OWNER, currency="IRR")
            .credit(_money("100"), reason="refund", source_reference="PAY-OLD", at=_AT)
            .wallet
        )
        use_case, _, _, _ = _build_credit(wallets=wallets)

        use_case.execute(_credit_command(amount="50"))

        assert wallets.get_for_owner(_OWNER).balance == _money("150")

    def test_records_a_money_audit_entry_with_before_and_after_balance(self) -> None:
        use_case, _, _, audit = _build_credit()

        use_case.execute(_credit_command())

        assert len(audit.records) == 1
        record = audit.records[0]
        assert record["action"] == "wallet.credited"
        assert record["resource_type"] == "wallet"
        assert record["actor"] == "u:1"
        balance_change = next(c for c in record["changes"] if c.field == "balance")
        assert balance_change.before == "0"
        assert balance_change.after == "150.00"

    def test_is_idempotent_on_a_repeated_source_reference(self) -> None:
        use_case, wallets, _, audit = _build_credit()

        first = use_case.execute(_credit_command())
        second = use_case.execute(_credit_command())  # same source reference

        assert first.id == second.id  # the same stored entry is returned
        assert wallets.get_for_owner(_OWNER).balance == _money("150.00")  # not doubled
        assert len(audit.records) == 1  # only the first credit was audited

    def test_a_null_source_reference_is_never_deduplicated(self) -> None:
        use_case, wallets, _, _ = _build_credit()

        use_case.execute(_credit_command(source_reference=None))
        use_case.execute(_credit_command(source_reference=None))

        assert wallets.get_for_owner(_OWNER).balance == _money("300.00")

    def test_rolls_back_on_a_currency_mismatch(self) -> None:
        wallets = FakeWallets()
        wallets.seed(Wallet.empty(owner=_OWNER, currency="USD"))
        use_case, _, uow, _ = _build_credit(wallets=wallets)

        with pytest.raises(WalletCurrencyMismatchError):
            use_case.execute(_credit_command())  # IRR credit onto a USD wallet

        assert uow.rolled_back is True
        assert uow.committed is False

    def test_logs_the_credit_without_the_amount(self) -> None:
        use_case, _, _, _ = _build_credit()

        with capture_logs() as logs:
            use_case.execute(_credit_command())

        event = next(log for log in logs if log["event"] == "wallet_credited")
        assert "amount" not in event  # money detail lives on the audit entry, not the log
        assert event["currency"] == "IRR"


# --- DebitWallet ---------------------------------------------------------


def _build_debit(
    *, wallets: FakeWallets | None = None, uow: FakeUnitOfWork | None = None
) -> tuple[DebitWallet, FakeWallets, FakeUnitOfWork, RecordingAudit]:
    wallets = wallets or FakeWallets()
    uow = uow or FakeUnitOfWork()
    audit = RecordingAudit()
    use_case = DebitWallet(unit_of_work=uow, wallets=wallets, clock=FakeClock(), audit=audit)
    return use_case, wallets, uow, audit


def _debit_command(
    *, amount: str = "150.00", source_reference: str | None = "PAY-XYZ"
) -> DebitWalletCommand:
    return DebitWalletCommand(
        owner=_OWNER,
        amount=Decimal(amount),
        currency="IRR",
        reason="order_payment",
        actor=_OWNER,
        source_reference=source_reference,
    )


def _seed_funded(wallets: FakeWallets, balance: str) -> None:
    wallets.seed(
        Wallet.empty(owner=_OWNER, currency="IRR")
        .credit(_money(balance), reason="refund", source_reference="SEED", at=_AT)
        .wallet
    )


class TestDebitWallet:
    def test_debits_an_existing_wallet_and_records_a_ledger_entry(self) -> None:
        wallets = FakeWallets()
        _seed_funded(wallets, "150.00")
        use_case, _, uow, _ = _build_debit(wallets=wallets)

        txn = use_case.execute(_debit_command())

        assert txn.type == TransactionType.DEBIT
        assert txn.amount == _money("150.00")
        assert txn.balance_after == _money("0")
        assert wallets.get_for_owner(_OWNER).balance == _money("0")
        assert uow.committed is True
        assert wallets.locked == [_OWNER]  # the wallet row was locked

    def test_leaves_the_remaining_balance_on_a_partial_spend(self) -> None:
        wallets = FakeWallets()
        _seed_funded(wallets, "150.00")
        use_case, _, _, _ = _build_debit(wallets=wallets)

        use_case.execute(_debit_command(amount="60.00"))

        assert wallets.get_for_owner(_OWNER).balance == _money("90.00")

    def test_records_a_money_audit_entry_with_before_and_after_balance(self) -> None:
        wallets = FakeWallets()
        _seed_funded(wallets, "150.00")
        use_case, _, _, audit = _build_debit(wallets=wallets)

        use_case.execute(_debit_command())

        assert len(audit.records) == 1
        record = audit.records[0]
        assert record["action"] == "wallet.debited"
        assert record["resource_type"] == "wallet"
        assert record["actor"] == _OWNER
        balance_change = next(c for c in record["changes"] if c.field == "balance")
        assert balance_change.before == "150.00"
        assert balance_change.after == "0.00"

    def test_refuses_a_debit_that_exceeds_the_balance_and_rolls_back(self) -> None:
        wallets = FakeWallets()
        _seed_funded(wallets, "100.00")
        use_case, _, uow, audit = _build_debit(wallets=wallets)

        with pytest.raises(InsufficientWalletFundsError):
            use_case.execute(_debit_command(amount="150.00"))

        assert wallets.get_for_owner(_OWNER).balance == _money("100.00")  # untouched
        assert uow.rolled_back is True
        assert uow.committed is False
        assert audit.records == []

    def test_refuses_a_debit_from_a_wallet_that_does_not_exist(self) -> None:
        use_case, wallets, uow, _ = _build_debit()

        with pytest.raises(InsufficientWalletFundsError):
            use_case.execute(_debit_command())

        assert wallets.get_for_owner(_OWNER) is None  # no wallet was created
        assert uow.rolled_back is True

    def test_is_idempotent_on_a_repeated_source_reference(self) -> None:
        wallets = FakeWallets()
        _seed_funded(wallets, "150.00")
        use_case, _, _, audit = _build_debit(wallets=wallets)

        first = use_case.execute(_debit_command(amount="150.00"))
        second = use_case.execute(_debit_command(amount="150.00"))  # same source reference

        assert first.id == second.id  # the same stored entry is returned
        assert wallets.get_for_owner(_OWNER).balance == _money("0")  # not debited twice
        assert len(audit.records) == 1  # only the first debit was audited

    def test_logs_the_debit_without_the_amount(self) -> None:
        wallets = FakeWallets()
        _seed_funded(wallets, "150.00")
        use_case, _, _, _ = _build_debit(wallets=wallets)

        with capture_logs() as logs:
            use_case.execute(_debit_command())

        event = next(log for log in logs if log["event"] == "wallet_debited")
        assert "amount" not in event  # money detail lives on the audit entry, not the log
        assert event["currency"] == "IRR"


# --- GetMyWallet ---------------------------------------------------------


class TestGetMyWallet:
    def test_returns_an_empty_wallet_when_none_exists(self) -> None:
        wallets = FakeWallets()
        use_case = GetMyWallet(wallets=wallets, default_currency="IRR")

        view = use_case.execute(owner=_OWNER)

        assert view.balance == _money("0")
        assert view.transactions == ()

    def test_returns_the_balance_and_recent_transactions(self) -> None:
        credit, wallets, _, _ = _build_credit()
        credit.execute(_credit_command(amount="100", source_reference="A"))
        credit.execute(_credit_command(amount="50", source_reference="B"))
        use_case = GetMyWallet(wallets=wallets, default_currency="IRR")

        view = use_case.execute(owner=_OWNER)

        assert view.balance == _money("150")
        assert len(view.transactions) == 2

    def test_is_owner_scoped(self) -> None:
        credit, wallets, _, _ = _build_credit()
        credit.execute(_credit_command())
        use_case = GetMyWallet(wallets=wallets, default_currency="IRR")

        other = use_case.execute(owner="u:999")

        assert other.balance == _money("0")  # another user's wallet is invisible
