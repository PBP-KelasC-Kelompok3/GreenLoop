from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("courier", "0006_merge_courier_0005"),
    ]

    operations = [
        migrations.DeleteModel(
            name="CollectionPoint",
        ),
    ]
