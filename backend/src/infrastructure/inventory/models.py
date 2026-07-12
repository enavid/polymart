"""Django ORM models for the inventory context.

A ``StockSourceModel`` is a warehouse/location. A ``StockLevelModel`` is the stock of one
variant (referenced by SKU string, deliberately not a FK into the catalog so the contexts
stay decoupled) at one source: a physical ``on_hand`` count and a ``reserved`` count held
against open orders. The ``unique(sku, source)`` constraint means one level row per
variant-source pair, so the atomic reserve/adjust locks a single row.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class StockSourceModel(models.Model):
    """A stock source (warehouse/location)."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "inventory"
        db_table = "inventory_stock_source"
        # The object-scoped management permission (two-layer RBAC); mirrors
        # src.domain.inventory.permissions.MANAGE_STOCK_SOURCE. Declared here so
        # create_permissions binds it to this content type for per-source guardian grants.
        permissions: ClassVar[list[tuple[str, str]]] = [  # type: ignore[assignment]
            ("manage_stock_source", "Can manage stock sources (create, set/adjust stock)"),
        ]

    def __str__(self) -> str:
        return self.code


class StockLevelModel(models.Model):
    """A variant's stock at one source: physical on-hand and reserved counts."""

    sku = models.CharField(max_length=64, db_index=True)
    source = models.ForeignKey(StockSourceModel, related_name="levels", on_delete=models.CASCADE)
    on_hand = models.PositiveIntegerField(default=0)
    reserved = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "inventory"
        db_table = "inventory_stock_level"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["sku", "source"], name="uniq_stock_level_sku_source"),
            # Reserved can never exceed the physical count -- the level invariant,
            # enforced at the database as a backstop to the domain's guard.
            models.CheckConstraint(
                condition=models.Q(reserved__lte=models.F("on_hand")),
                name="ck_stock_level_reserved_le_on_hand",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.sku}@{self.source_id}:{self.on_hand}/{self.reserved}"


class StockPolicyModel(models.Model):
    """Per-variant (``sku``) selling policy the physical levels cannot express.

    ``backorderable`` lets a variant be sold beyond its physical available-to-promise; the
    overflow is tracked in ``backordered`` (units promised with no physical backing yet), so
    the per-source ``reserved <= on_hand`` invariant is never violated by a backorder.
    ``low_stock_threshold`` is the available count at or below which a low-stock alert fires
    (0 disables it). One row per SKU; absent means the default (no backorder, no alert).
    """

    sku = models.CharField(max_length=64, unique=True)
    backorderable = models.BooleanField(default=False)
    low_stock_threshold = models.PositiveIntegerField(default=0)
    backordered = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "inventory"
        db_table = "inventory_stock_policy"

    def __str__(self) -> str:
        flag = "backorder" if self.backorderable else "no-backorder"
        return f"{self.sku}:{flag}:threshold={self.low_stock_threshold}"
