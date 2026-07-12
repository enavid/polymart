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
from django.db.models import Q

_ORDER_NUMBER_MAX_LENGTH = 40
_CHANNEL_SLUG_MAX_LENGTH = 64
# A guest owner is identified by the same CSPRNG session token as their cart (~43 url-safe
# base64 chars for 32 bytes); 64 leaves headroom.
_GUEST_TOKEN_MAX_LENGTH = 64
_CURRENCY_CODE_MAX_LENGTH = 3
_SKU_MAX_LENGTH = 64
# Widened from 16 to fit the longest status token ("ready_for_pickup") with headroom.
_STATUS_MAX_LENGTH = 24
# Captured fulfilment (carrier + tracking) lengths mirror the order domain's Fulfillment VO.
_CARRIER_MAX_LENGTH = 120
_TRACKING_NUMBER_MAX_LENGTH = 128
_TRACKING_URL_MAX_LENGTH = 500
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
# Captured shipping-method code/name lengths mirror the shipping context's stored precision.
_SHIPPING_METHOD_CODE_MAX_LENGTH = 32
_SHIPPING_METHOD_NAME_MAX_LENGTH = 120
# A captured tax rate is a percentage (0..100) with up to 4 decimal places: 100.0000 needs
# 3 + 4 = 7 significant digits.
_TAX_RATE_MAX_DIGITS = 7
_TAX_RATE_DECIMAL_PLACES = 4


class OrderModel(models.Model):
    """A placed order (one row per order).

    The owner is either a signed-in user (a hard FK, cascade-deleted with the user) or an
    anonymous guest (the ``guest_token`` from their session cookie); a check constraint
    enforces that exactly one is set, mirroring the cart's dual-column ownership. The
    channel is a soft slug reference -- the channel lives in a separate bounded context
    and is never deleted out from under an order -- matching how the catalog references
    channels. ``number`` is the public, unguessable, unique reference used in URLs.
    """

    number = models.CharField(max_length=_ORDER_NUMBER_MAX_LENGTH, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="orders",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    # NULL (never "") is the "no guest owner" sentinel, so the check constraint can tell a
    # guest order (owner NULL, token set) from a user order (owner set, token NULL) via IS
    # NULL. A guest order is intentionally not cascade-reaped; a later job expires old ones.
    guest_token = models.CharField(  # noqa: DJ001 - NULL is the "no guest owner" sentinel
        max_length=_GUEST_TOKEN_MAX_LENGTH, null=True, blank=True
    )
    channel_slug = models.SlugField(max_length=_CHANNEL_SLUG_MAX_LENGTH)
    currency_code = models.CharField(max_length=_CURRENCY_CODE_MAX_LENGTH)
    # ``total`` is the grand total (goods + shipping). Shipping is captured at placement like
    # a line's price: a later change to the channel's configured rates never rewrites a placed
    # order. ``shipping_method_code`` is "" for an order with no delivery charge (e.g. a manual
    # pre-invoice); the mapper reads that as "no captured shipping". Existing rows predate
    # shipping, so the migration backfills 0 / "" (which the aggregate reads as no shipping).
    shipping_cost = models.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES, default=0
    )
    shipping_method_code = models.CharField(
        max_length=_SHIPPING_METHOD_CODE_MAX_LENGTH, blank=True, default=""
    )
    shipping_method_name = models.CharField(
        max_length=_SHIPPING_METHOD_NAME_MAX_LENGTH, blank=True, default=""
    )
    # A pickup (BOPIS) method captures no shipping address and follows the
    # ready-for-pickup -> picked-up lifecycle; a delivery method ships to the captured
    # address and follows fulfilled. Existing/legacy rows are deliveries (False).
    shipping_is_pickup = models.BooleanField(default=False)
    # Captured tax, at placement like a line's price: a later change to the channel's rate never
    # rewrites a placed order. ``tax_rate`` is NULL (never 0) for an order in an untaxed channel
    # and for orders that predate tax; the mapper reads NULL as "no captured tax" (total
    # unchanged). A configured rate of 0 is distinct from NULL -- it captures a 0-amount tax line.
    tax_amount = models.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES, default=0
    )
    tax_rate = models.DecimalField(
        max_digits=_TAX_RATE_MAX_DIGITS,
        decimal_places=_TAX_RATE_DECIMAL_PLACES,
        null=True,
        blank=True,
    )
    total = models.DecimalField(
        max_digits=_AMOUNT_MAX_DIGITS, decimal_places=_AMOUNT_DECIMAL_PLACES
    )
    status = models.CharField(max_length=_STATUS_MAX_LENGTH)
    placed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Captured fulfilment for a shipped (delivery) order: the carrier and its tracking
    # reference staff entered when moving the order to FULFILLED (an optional tracking URL
    # the shopper can follow). "" means no shipment captured yet -- the mapper reads an
    # empty carrier as "no fulfillment". A pickup order never sets these.
    fulfillment_carrier = models.CharField(max_length=_CARRIER_MAX_LENGTH, blank=True, default="")
    fulfillment_tracking_number = models.CharField(
        max_length=_TRACKING_NUMBER_MAX_LENGTH, blank=True, default=""
    )
    fulfillment_tracking_url = models.CharField(
        max_length=_TRACKING_URL_MAX_LENGTH, blank=True, default=""
    )

    # Shipping address, captured at placement (copied from the address book, not a
    # foreign key -- a later edit/deletion of the saved address must never rewrite a
    # placed order's history). ``shipping_line2`` is optional. A pickup (BOPIS) order
    # captures no address, so an all-blank recipient reads as "no captured address"
    # (mirroring how an empty shipping_method_code reads as "no captured shipping").
    shipping_recipient_name = models.CharField(
        max_length=_RECIPIENT_NAME_MAX_LENGTH, blank=True, default=""
    )
    shipping_phone_number = models.CharField(
        max_length=_PHONE_NUMBER_MAX_LENGTH, blank=True, default=""
    )
    shipping_province = models.CharField(max_length=_PROVINCE_MAX_LENGTH, blank=True, default="")
    shipping_city = models.CharField(max_length=_CITY_MAX_LENGTH, blank=True, default="")
    shipping_postal_code = models.CharField(
        max_length=_POSTAL_CODE_MAX_LENGTH, blank=True, default=""
    )
    shipping_line1 = models.CharField(max_length=_ADDRESS_LINE_MAX_LENGTH, blank=True, default="")
    shipping_line2 = models.CharField(max_length=_ADDRESS_LINE_MAX_LENGTH, blank=True, default="")

    class Meta:
        app_label = "order"
        db_table = "order_order"
        # Newest first: the default read order for a shopper's history.
        ordering = ("-id",)
        # codename mirrors src.domain.order.permissions.MANAGE_ORDERS. Hosting it on the
        # order content type lets the registry sync resolve it by app_label="order".
        permissions: ClassVar[list[tuple[str, str]]] = [  # type: ignore[assignment]
            ("manage_orders", "Can manage orders (create manual orders and issue pre-invoices)"),
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["owner", "-id"], name="idx_order_owner_recent"),
            # Guest history is scoped by token; a matching index keeps that read cheap.
            models.Index(fields=["guest_token", "-id"], name="idx_order_guest_recent"),
        ]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            # Exactly one owner kind: a user FK or a guest token, never both, never neither.
            models.CheckConstraint(
                name="order_exactly_one_owner",
                condition=(
                    Q(owner__isnull=False, guest_token__isnull=True)
                    | Q(owner__isnull=True, guest_token__isnull=False)
                ),
            ),
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
