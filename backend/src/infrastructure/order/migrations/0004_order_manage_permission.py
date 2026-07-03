# Manual orders / pre-invoices (final Phase 3 slice): host the manage_orders custom
# permission on the order content type so the RBAC registry sync can resolve it by
# app_label="order". See ADR 0036.
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0003_order_guest_ownership'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='ordermodel',
            options={'ordering': ('-id',), 'permissions': [('manage_orders', 'Can manage orders (create manual orders and issue pre-invoices)')], 'verbose_name': 'order', 'verbose_name_plural': 'orders'},
        ),
    ]
