"""Retire the legacy single-count catalog stock table.

The inventory context is now the source of truth for on-hand stock. Inventory
migration ``0002`` folds every ``catalog_variant_stock`` row into the default source, so
this migration depends on it to guarantee the data is moved before the table is dropped.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0015_productmodel_is_published"),
        ("inventory", "0002_seed_default_source_and_backfill"),
    ]

    operations = [
        migrations.DeleteModel(name="VariantStockModel"),
    ]
