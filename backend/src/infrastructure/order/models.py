"""Django ORM models for order persistence.

Infrastructure detail, intentionally separate from the domain aggregate. The
repository maps between the two so the domain never depends on the ORM. An order's
lines live in a child table (one row per variant) with the *captured* unit price and
line total, so a persisted order stays self-describing even after the catalog price
changes.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models

_ORDER_NUMBER_MAX_LENGTH = 40
_CHANNEL_SLUG_MAX_LENGTH = 64
_CURRENCY_CODE_MAX_LENGTH = 3
_SKU_MAX_LENGTH = 64
_STATUS_MAX_LENGTH = 16
# Money precision mirrors the catalog's stored precision, so a captured price/total is
# persisted losslessly (18 total digits, 4 decimal places).
_AMOUNT_MAX_DIGITS = 18
_AMOUNT_DECIMAL_PLACES = 4
# Shipping-address field lengths mirror the address context's stored precision (the
# value is a snapshot copied from an already-validated Address row).
_RECIPIENT_NAME_MAX_LENGTH = 200
_PHONE_NUMBER_MAX_LENGTH = 20
_PROVINCE_MAX_LENGTH = 100
_CITY_MAX_LENGTH = 100
_POSTAL_CODE_MAX_LENGTH = 10
_ADDRESS_LINE_MAX_LENGTH = 255


class OrderModel(models.Model):
    """A placed order (one row per order).

    The owner is a hard FK to the user (an order is meaningless without its owner). The
    channel is a soft slug reference -- the channel lives in a separate bounded context
    and is never deleted out from under an order -- matching how the catalog references
    channels. ``number`` is the public, unguessable, unique reference used in URLs.
    """

    number = models.CharField(max_length=_ORDER_NUMBER_MAX_LENGTH, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="orders",
        on_delete=models.CASCADE,
    )
    channel_slug = models.SlugField(max_length=_CHANNEL_SLUG_MAX_LENGTH)
    currency_code = models.CharField(max_length=_CURRENCY_CODE_MAX_LENGTH)
    total = models.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES
    )
    status = models.CharField(max_length=_STATUS_MAX_LENGTH)
    placed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Shipping address, captured at placement (copied from the address book, not a
    # foreign key -- a later edit/deletion of the saved address must never rewrite a
    # placed order's history). ``shipping_line2`` is the only optional field. Every new
    # order supplies a real captured address (enforced by the domain aggregate and the
    # repository), so these are NOT NULL with no model-level default; the initial
    # migration backfills any pre-existing rows with "" one-off (preserve_default=False).
    shipping_recipient_name = models.CharField(max_length=_RECIPIENT_NAME_MAX_LENGTH)
    shipping_phone_number = models.CharField(max_length=_PHONE_NUMBER_MAX_LENGTH)
    shipping_province = models.CharField(max_length=_PROVINCE_MAX_LENGTH)
    shipping_city = models.CharField(max_length=_CITY_MAX_LENGTH)
    shipping_postal_code = models.CharField(max_length=_POSTAL_CODE_MAX_LENGTH)
    shipping_line1 = models.CharField(max_length=_ADDRESS_LINE_MAX_LENGTH)
    shipping_line2 = models.CharField(max_length=_ADDRESS_LINE_MAX_LENGTH, blank=True, default="")

    class Meta:
        app_label = "order"
        db_table = "order_order"
        # Newest first: the default read order for a shopper's history.
        ordering = ("-id",)
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["owner", "-id"], name="idx_order_owner_recent"),
        ]
        verbose_name = "order"
        verbose_name_plural = "orders"

    def __str__(self) -> str:
        return self.number


class OrderLineModel(models.Model):
    """One captured line of an order: what was bought, how many, at what price.

    ``unit_price`` and ``line_total`` are snapshots taken at placement; they are stored
    rather than recomputed, so the order is immune to later catalog price changes.
    """

    order = models.ForeignKey(OrderModel, related_name="lines", on_delete=models.CASCADE)
    sku = models.CharField(max_length=_SKU_MAX_LENGTH)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES
    )
    line_total = models.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        app_label = "order"
        db_table = "order_order_line"
        ordering = ("position",)
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["order", "sku"], name="uniq_line_sku_per_order"),
        ]

    def __str__(self) -> str:
        return f"{self.order_id}:{self.sku}:{self.quantity}"
