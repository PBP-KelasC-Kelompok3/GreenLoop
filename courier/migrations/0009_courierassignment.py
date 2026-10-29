from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_existing_assignments(apps, schema_editor):
    PickupSchedule = apps.get_model("scheduling", "PickupSchedule")
    CourierAssignment = apps.get_model("courier", "CourierAssignment")
    alias = schema_editor.connection.alias

    rows = PickupSchedule.objects.using(alias).exclude(courier_id__isnull=True)
    for pickup in rows.iterator():
        CourierAssignment.objects.using(alias).get_or_create(
            pickup_schedule_id=pickup.pk,
            defaults={"courier_id": pickup.courier_id},
        )


def restore_existing_assignments(apps, schema_editor):
    PickupSchedule = apps.get_model("scheduling", "PickupSchedule")
    CourierAssignment = apps.get_model("courier", "CourierAssignment")
    alias = schema_editor.connection.alias

    for assignment in CourierAssignment.objects.using(alias).iterator():
        PickupSchedule.objects.using(alias).filter(
            pk=assignment.pickup_schedule_id,
        ).update(courier_id=assignment.courier_id)


class Migration(migrations.Migration):
    dependencies = [
        ("courier", "0008_courierprofile_profile_photo"),
        ("scheduling", "0012_mitraprofile_profile_photo"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CourierAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                ("courier", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="courier_assignments",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("pickup_schedule", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="courier_assignment",
                    to="scheduling.pickupschedule",
                )),
            ],
            options={"ordering": ["assigned_at", "pk"]},
        ),
        migrations.RunPython(copy_existing_assignments, restore_existing_assignments),
    ]
