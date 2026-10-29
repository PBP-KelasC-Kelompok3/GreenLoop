import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scheduling", "0013_remove_pickupschedule_courier"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pickupschedule",
            name="armada",
            field=models.CharField(
                choices=[("Motor Box", "Motor Box"), ("Pickup Bak", "Pickup Bak")],
                default="Pickup Bak",
                max_length=50,
                verbose_name="Jenis Armada",
            ),
        ),
        migrations.AlterField(
            model_name="pickupschedule",
            name="estimated_weight",
            field=models.FloatField(
                help_text="Berat limbah dalam kg (maksimal 120 kg per pengajuan)",
                validators=[
                    django.core.validators.MinValueValidator(0.01),
                    django.core.validators.MaxValueValidator(
                        120,
                        message="Maksimal berat satu pengajuan adalah 120 kg. Pisahkan menjadi beberapa penjemputan.",
                    ),
                ],
            ),
        ),
    ]
