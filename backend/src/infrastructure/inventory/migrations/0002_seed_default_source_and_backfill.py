"""Seed the default stock source and fold existing catalog stock into it.

The multi-source model becomes the source of truth for stock. Every variant's single
on-hand count (catalog_variant_stock) is copied into a ``main`` level with reserved=0, so
no stock is lost and a single-source store behaves exactly as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps

DEFAULT_SOURCE_CODE = "main"
DEFAULT_SOURCE_NAME = "Main"


def seed_and_backfill(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    StockSourceModel = apps.get_model("inventory", "StockSourceModel")
    StockLevelModel = apps.get_model("inventory", "StockLevelModel")
    VariantStockModel = apps.get_model("catalog", "VariantStockModel")

    source, _ = StockSourceModel.objects.get_or_create(
        code=DEFAULT_SOURCE_CODE, defaults={"name": DEFAULT_SOURCE_NAME}
    )
    for stock in VariantStockModel.objects.select_related("variant").all():
        StockLevelModel.objects.update_or_create(
            sku=stock.variant.sku,
            source=source,
            defaults={"on_hand": stock.quantity, "reserved": 0},
        )


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    StockSourceModel = apps.get_model("inventory", "StockSourceModel")
    StockLevelModel = apps.get_model("inventory", "StockLevelModel")
    StockLevelModel.objects.filter(source__code=DEFAULT_SOURCE_CODE).delete()
    StockSourceModel.objects.filter(code=DEFAULT_SOURCE_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
        ("catalog", "0014_variantstockmodel"),
    ]

    operations = [migrations.RunPython(seed_and_backfill, unseed)]
