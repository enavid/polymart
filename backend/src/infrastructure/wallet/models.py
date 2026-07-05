"""Django ORM models for wallet persistence.

Infrastructure detail, intentionally separate from the domain aggregate. The repository
maps between the two so the domain never depends on the ORM. A wallet always belongs to a
registered user (a hard FK, one wallet per user); its ledger is an append-only set of
transactions. A transaction's ``source_reference`` (the payment reference that caused a
refund) is unique *per wallet* so a retried credit can never be recorded twice -- the
database-level backstop to the application's idempotency guard.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models

_CURRENCY_CODE_MAX_LENGTH = 3
_TYPE_MAX_LENGTH = 8
_REASON_MAX_LENGTH = 64
# A source reference is a payment reference (~40 chars); 64 leaves headroom.
_SOURCE_REFERENCE_MAX_LENGTH = 64
# Money precision mirrors the payment/order/catalog stored precision (18 total digits, 4
# decimal places) so a balance and any movement persist losslessly.
_AMOUNT_MAX_DIGITS = 18
_AMOUNT_DECIMAL_PLACES = 4


class WalletModel(models.Model):
    """A user's internal store-credit balance (one row per user).

    The balance is materialised (not derived by summing the ledger) and only ever updated
    under a row lock, so concurrent credits cannot lose an update. The currency is fixed on
    the first credit and every later movement must match it.
    """

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="wallet",
        on_delete=models.CASCADE,
    )
    balance = models.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES
    )
    currency_code = models.CharField(max_length=_CURRENCY_CODE_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "wallet"
        db_table = "wallet_wallet"
        verbose_name = "wallet"
        verbose_name_plural = "wallets"

    def __str__(self) -> str:
        return f"wallet:{self.owner_id}"


class WalletTransactionModel(models.Model):
    """One append-only ledger entry for a wallet (a single movement of value).

    ``balance_after`` is the wallet balance once this movement was applied, stored so a
    statement renders without replaying the ledger. ``source_reference`` ties the entry to
    what caused it and is unique per wallet (the idempotency backstop); it is NULL for a
    movement with no external cause.
    """

    wallet = models.ForeignKey(
        WalletModel,
        related_name="transactions",
        on_delete=models.CASCADE,
    )
    type = models.CharField(max_length=_TYPE_MAX_LENGTH)
    amount = models.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES
    )
    currency_code = models.CharField(max_length=_CURRENCY_CODE_MAX_LENGTH)
    reason = models.CharField(max_length=_REASON_MAX_LENGTH)
    balance_after = models.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES
    )
    # NULL (never "") is the "no external cause" sentinel, so the per-wallet unique
    # constraint below does not collapse multiple source-less movements together.
    source_reference = models.CharField(  # noqa: DJ001 - NULL is the "no source" sentinel
        max_length=_SOURCE_REFERENCE_MAX_LENGTH, null=True, blank=True
    )
    # Captured from the domain clock at movement time (not auto_now_add), so the mapper
    # round-trips the exact instant the aggregate recorded.
    created_at = models.DateTimeField()

    class Meta:
        app_label = "wallet"
        db_table = "wallet_transaction"
        # Newest first: the default order for rendering a statement.
        ordering: ClassVar = ("-id",)
        constraints: ClassVar[list[models.BaseConstraint]] = [
            # At most one movement per (wallet, source_reference), enforced in the database
            # so two concurrent refunds of the same payment cannot both credit -- the
            # idempotency guarantee, independent of the application-layer probe. NULL sources
            # are excluded (a Postgres partial unique), so source-less movements are unbounded.
            models.UniqueConstraint(
                fields=["wallet", "source_reference"],
                condition=models.Q(source_reference__isnull=False),
                name="uniq_wallet_transaction_source",
            ),
        ]
        verbose_name = "wallet transaction"
        verbose_name_plural = "wallet transactions"

    def __str__(self) -> str:
        return f"{self.type}:{self.amount} (wallet {self.wallet_id})"
