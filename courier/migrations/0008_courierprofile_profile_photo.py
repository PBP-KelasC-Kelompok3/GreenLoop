from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('courier', '0007_remove_collectionpoint'),
    ]

    operations = [
        migrations.AddField(
            model_name='courierprofile',
            name='profile_photo',
            field=models.ImageField(blank=True, upload_to='profile_photos/courier/'),
        ),
    ]
