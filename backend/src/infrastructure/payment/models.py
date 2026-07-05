"""Django ORM models for payment persistence.

Infrastructure detail, intentionally separate from the domain aggregate. The repository
maps between the two so the domain never depends on the ORM. A payment references its
order by the order's public *number* (a soft reference, not a foreign key): the order
lives in a separate bounded context, so the two are coupled only through that opaque
handle, exactly as the catalog and order contexts reference a channel by slug.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q

from src.domain.payment.value_objects import ACTIVE_PAYMENT_STATUSES

_PAYMENT_REFERENCE_MAX_LENGTH = 40
_ORDER_NUMBER_MAX_LENGTH = 40
# A guest owner is identified by the same CSPRNG session token as their cart/order (~43
# url-safe base64 chars for 32 bytes); 64 leaves headroom.
_GUEST_TOKEN_MAX_LENGTH = 64
_CURRENCY_CODE_MAX_LENGTH = 3
_METHOD_MAX_LENGTH = 16
_STATUS_MAX_LENGTH = 16
# Money precision mirrors the order/catalog stored precision, so a captured amount is
# persisted losslessly (18 total digits, 4 decimal places).
_AMOUNT_MAX_DIGITS = 18
_AMOUNT_DECIMAL_PLACES = 4

# The persisted status values that still hold an order (single source of truth from the
# domain), used to build the "at most one active payment per order" partial constraint.
_ACTIVE_STATUS_VALUES = sorted(status.value for status in ACTIVE_PAYMENT_STATUSES)


class PaymentModel(models.Model):
    """A payment against one order (one row per payment attempt).

    The owner is either a signed-in user (a hard FK, cascade-deleted with the user) or an
    anonymous guest (the ``guest_token`` from their session cookie); a check constraint
    enforces that exactly one is set, mirroring the cart/order dual-column ownership. The
    order is a soft ``order_number`` reference (no cross-context FK). ``reference`` is the
    public, unguessable, unique handle used in URLs.
    """

    reference = models.CharField(max_length=_PAYMENT_REFERENCE_MAX_LENGTH, unique=True)
    order_number = models.CharField(max_length=_ORDER_NUMBER_MAX_LENGTH)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="payments",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    # NULL (never "") is the "no guest owner" sentinel, so the check constraint can tell a
    # guest payment (owner NULL, token set) from a user payment via IS NULL.
    guest_token = models.CharField(  # noqa: DJ001 - NULL is the "no guest owner" sentinel
        max_length=_GUEST_TOKEN_MAX_LENGTH, null=True, blank=True
    )
    method = models.CharField(max_length=_METHOD_MAX_LENGTH)
    amount = models.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES
    )
    currency_code = models.CharField(max_length=_CURRENCY_CODE_MAX_LENGTH)
    status = models.CharField(max_length=_STATUS_MAX_LENGTH)
    # Captured from the domain clock at initiation (not auto_now_add), so the mapper
    # round-trips the exact instant the aggregate recorded.
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "payment"
        db_table = "payment_payment"
        # Newest first: the default order for reading an order's most recent payment.
        ordering = ("-id",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["owner", "order_number"], name="idx_payment_owner_order"),
            models.Index(fields=["guest_token", "order_number"], name="idx_payment_guest_order"),
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            # Exactly one owner kind: a user FK or a guest token, never both, never neither.
            models.CheckConstraint(
                name="payment_exactly_one_owner",
                condition=(
                    Q(owner__isnull=False, guest_token__isnull=True)
                    | Q(owner__isnull=True, guest_token__isnull=False)
                ),
            ),
            # At most one *active* (pending/authorized/captured) payment per order, enforced
            # in the database so two concurrent initiations cannot both create one -- the
            # anti-double-payment guarantee, independent of the application-layer guard. A
            # spent payment (failed/cancelled/voided) is excluded, so a fresh attempt is
            # allowed after a failure.
            models.UniqueConstraint(
                fields=["order_number"],
                condition=Q(status__in=_ACTIVE_STATUS_VALUES),
                name="uniq_active_payment_per_order",
            ),
        ]
        verbose_name = "payment"
        verbose_name_plural = "payments"

    def __str__(self) -> str:
        return self.reference
