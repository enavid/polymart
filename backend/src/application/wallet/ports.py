"""Ports (interfaces) for the wallet use cases.

The application layer depends only on these abstractions; concrete adapters (Django ORM,
a real clock, in-memory fakes) live elsewhere and are injected at the composition root,
keeping the dependency rule pointing inward.

A wallet is owner-scoped by construction: every read and every write is keyed by the
opaque owner id (``u:<pk>`` -- a wallet always belongs to a registered user), so one
shopper can never reach another's wallet. The ``source_reference`` on a transaction is the
idempotency key: the repository can answer whether a movement for a given source was
already recorded, so a retried credit (e.g. a repeated refund) never double-credits.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import datetime

from src.domain.wallet.entities import Wallet, WalletMovement, WalletTransaction


class WalletRepository(ABC):
    """Persistence boundary for the Wallet aggregate and its ledger.

    All reads are scoped to the owner, so one user can never resolve another's wallet.
    """

    @abstractmethod
    def get_for_owner(self, owner: str) -> Wallet | None:
        """Return the owner's wallet (a plain, unlocked read), or ``None`` if none exists."""

    @abstractmethod
    def get_for_update(self, owner: str) -> Wallet | None:
        """Return the owner's wallet under a row lock, or ``None`` if none exists.

        Used by a credit, which must serialize concurrent movements on the same wallet so a
        lost update cannot corrupt the balance.
        """

    @abstractmethod
    def create(self, wallet: Wallet) -> Wallet:
        """Persist a brand-new (zero-balance) wallet and return it with its assigned id."""

    @abstractmethod
    def save_movement(self, movement: WalletMovement) -> WalletTransaction:
        """Persist a movement: update the wallet's balance and append the ledger entry.

        The wallet in ``movement`` already carries its id; both writes happen together (the
        caller runs this inside a transaction), so the stored balance and the ledger never
        diverge. Returns the persisted transaction with its assigned id.
        """

    @abstractmethod
    def find_transaction_by_source(
        self, owner: str, source_reference: str
    ) -> WalletTransaction | None:
        """Return the owner's ledger entry for ``source_reference``, or ``None``.

        The idempotency probe: if a movement for this source was already recorded, the
        caller returns it unchanged rather than crediting again.
        """

    @abstractmethod
    def list_transactions(self, owner: str, *, limit: int) -> Sequence[WalletTransaction]:
        """Return the owner's most recent ledger entries (newest first), capped at ``limit``."""


class Clock(ABC):
    """Source of the current time, injected so ledger timestamps are testable.

    The wallet context owns its own ``Clock`` port (the dependency rule keeps contexts
    decoupled); the trivial system adapter lives in infrastructure.
    """

    @abstractmethod
    def now(self) -> datetime:
        """Return the current timezone-aware time."""


class UnitOfWork(ABC):
    """The transaction boundary for a wallet credit.

    ``atomic()`` returns a context manager; the idempotency probe, the lock/create, the
    balance update, the ledger append, and the audit write all commit together or roll back
    together on any exception.
    """

    @abstractmethod
    def atomic(self) -> AbstractContextManager[None]:
        """Return a context manager that runs its body as one atomic transaction."""
