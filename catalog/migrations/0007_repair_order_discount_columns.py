from django.db import migrations

from catalog.migration_compat import EnsureFields


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_merge_catalog_migration_histories"),
    ]

    operations = [
        EnsureFields(
            ("catalog", "Order"),
            ("goods_discount", "shipping_discount", "user_voucher"),
        ),
    ]
