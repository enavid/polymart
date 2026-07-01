"""Django ORM models for cart persistence.

Infrastructure detail, intentionally separate from the domain entities. The
repository maps between the two so the domain never depends on the ORM. A cart's
lines live in a child table (one row per variant) so each is individually
constrained (a variant appears at most once per cart).
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models

_CHANNEL_SLUG_MAX_LENGTH = 64
_SKU_MAX_LENGTH = 64


class CartModel(models.Model):
    """A shopper's cart for one channel (one row per owner per channel).

    The owner is a hard FK to the user (a cart is meaningless without its owner and
    dies with them). The channel is a soft slug reference: the channel lives in a
    separate bounded context and is never deleted out from under a cart, so no
    cross-app FK is used -- matching how the catalog references channels for pricing.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="carts", on_delete=models.CASCADE
    )
    channel_slug = models.SlugField(max_length=_CHANNEL_SLUG_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "cart"
        db_table = "cart_cart"
        ordering = ("id",)
        verbose_name = "cart"
        verbose_name_plural = "carts"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["owner", "channel_slug"], name="uniq_cart_per_owner_channel"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.owner_id}:{self.channel_slug}"


class CartLineModel(models.Model):
    """One variant in a cart, with the quantity intended for purchase."""

    cart = models.ForeignKey(CartModel, related_name="lines", on_delete=models.CASCADE)
    sku = models.CharField(max_length=_SKU_MAX_LENGTH)
    quantity = models.PositiveIntegerField()
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        app_label = "cart"
        db_table = "cart_cart_line"
        ordering = ("position",)
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["cart", "sku"], name="uniq_line_sku_per_cart"),
        ]

    def __str__(self) -> str:
        return f"{self.cart_id}:{self.sku}:{self.quantity}"
