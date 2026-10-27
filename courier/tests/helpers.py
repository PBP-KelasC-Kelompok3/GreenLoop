"""Bantuan yang dipakai bersama oleh semua file test courier."""
from django.contrib.auth.models import User

from accounts.models import UserProfile

# Test runner memakai DEBUG=False; storage manifest butuh collectstatic.
PLAIN_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def make_user(username="budi", role="courier", **extra):
    """Buat user dengan role tertentu."""
    user = User.objects.create_user(
        username, email=f"{username}@greenloop.id", password="pw12345!", **extra
    )
    UserProfile.objects.filter(user=user).update(role=role)
    return user