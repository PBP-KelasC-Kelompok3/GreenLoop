from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(choices=[('consumer', 'Consumer'), ('mitra', 'Mitra'), ('courier', 'Courier'), ('admin', 'Admin')], default='consumer', max_length=20),
        ),
    ]
