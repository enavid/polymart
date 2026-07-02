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
_GUEST_TOKEN_MAX_LENGTH = 64


class CartModel(models.Model):
    """A shopper's cart for one channel (one row per owner per channel).

    A cart belongs either to a signed-in user (the ``owner`` FK) or to an anonymous
    guest identified by an opaque session token (``guest_token``) -- exactly one of the
    two is set, enforced by a check constraint. The user FK cascades (a cart dies with
    its user); a guest cart has no user and is reaped by token expiry/cleanup instead.
    The channel is a soft slug reference: the channel lives in a separate bounded
    context and is never deleted out from under a cart, so no cross-app FK is used --
    matching how the catalog references channels for pricing.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="carts",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    # NULL (not "") is intentional: the "exactly one owner" check constraint and the
    # partial unique index distinguish "no guest token" from a real one via IS NULL, so
    # an empty string would masquerade as a value. Hence null=True on a CharField.
    guest_token = models.CharField(  # noqa: DJ001 - NULL is the "no guest owner" sentinel
        max_length=_GUEST_TOKEN_MAX_LENGTH, null=True, blank=True
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
            # Exactly one owner kind per cart: a user FK xor a guest token.
            models.CheckConstraint(
                name="cart_exactly_one_owner",
                condition=(
                    models.Q(owner__isnull=False, guest_token__isnull=True)
                    | models.Q(owner__isnull=True, guest_token__isnull=False)
                ),
            ),
            # One active cart per owner+channel, enforced per owner kind via partial
            # unique indexes (a plain (owner, channel) unique would ignore guest rows,
            # whose owner is NULL).
            models.UniqueConstraint(
                fields=["owner", "channel_slug"],
                condition=models.Q(owner__isnull=False),
                name="uniq_cart_per_user_channel",
            ),
            models.UniqueConstraint(
                fields=["guest_token", "channel_slug"],
                condition=models.Q(guest_token__isnull=False),
                name="uniq_cart_per_guest_channel",
            ),
        ]

    def __str__(self) -> str:
        owner = self.owner_id if self.owner_id is not None else self.guest_token
        return f"{owner}:{self.channel_slug}"


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
