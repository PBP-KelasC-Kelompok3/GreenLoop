from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("catalog", "0007_repair_order_discount_columns")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="weight_grams",
            field=models.PositiveIntegerField(
                default=500,
                help_text="Berat satuan untuk kalkulasi ongkir",
            ),
        ),
    ]
