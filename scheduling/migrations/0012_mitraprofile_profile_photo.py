from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('scheduling', '0011_pickupschedule_courier'),
    ]

    operations = [
        migrations.AddField(
            model_name='mitraprofile',
            name='profile_photo',
            field=models.ImageField(blank=True, upload_to='profile_photos/mitra/'),
        ),
    ]
