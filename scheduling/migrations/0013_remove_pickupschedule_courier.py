from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("courier", "0009_courierassignment"),
        ("scheduling", "0012_mitraprofile_profile_photo"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="pickupschedule",
            name="courier",
        ),
    ]
