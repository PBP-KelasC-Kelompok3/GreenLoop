from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('waste_reward', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='uservoucher',
            name='used_order_reference',
            field=models.CharField(blank=True, max_length=80, null=True, unique=True),
        ),
    ]
