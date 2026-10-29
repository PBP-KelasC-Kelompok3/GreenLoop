from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("courier", "0004_pickuprecord"),
        ("scheduling", "0011_pickupschedule_courier"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="pickuprecord",
            name="pickup_schedule",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="courier_record", to="scheduling.pickupschedule",
            ),
        ),
        migrations.AddField(
            model_name="weightlog",
            name="pickup_schedule",
            field=models.OneToOneField(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="weight_log", to="scheduling.pickupschedule",
            ),
        ),
    ]
