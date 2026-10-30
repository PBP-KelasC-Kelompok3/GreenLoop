from django.db import migrations


def set_admin_profiles(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    UserProfile.objects.filter(user__is_superuser=True).update(role="admin")
    UserProfile.objects.filter(user__is_staff=True).update(role="admin")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_alter_userprofile_role")]
    operations = [migrations.RunPython(set_admin_profiles, migrations.RunPython.noop)]
