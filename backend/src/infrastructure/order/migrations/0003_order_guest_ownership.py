# Guest order ownership (slice B of guest checkout): let an order be owned by an
# anonymous guest (guest_token) as well as a user, mirroring the cart's dual-column
# ownership. See ADR 0033.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0002_ordermodel_shipping_city_ordermodel_shipping_line1_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='ordermodel',
            name='guest_token',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name='ordermodel',
            name='owner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='orders', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddIndex(
            model_name='ordermodel',
            index=models.Index(fields=['guest_token', '-id'], name='idx_order_guest_recent'),
        ),
        migrations.AddConstraint(
            model_name='ordermodel',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('guest_token__isnull', True), ('owner__isnull', False)), models.Q(('guest_token__isnull', False), ('owner__isnull', True)), _connector='OR'), name='order_exactly_one_owner'),
        ),
    ]
