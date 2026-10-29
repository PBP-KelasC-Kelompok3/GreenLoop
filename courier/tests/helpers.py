"""Bantuan yang dipakai bersama oleh semua file test courier."""
from django.contrib.auth.models import User

from accounts.models import UserProfile
from courier.models import CourierProfile

# Test runner memakai DEBUG=False; storage manifest butuh collectstatic.
PLAIN_STATIC = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def make_user(username="budi", role="courier", courier_approved=None, **extra):
    """Buat user dengan role tertentu."""
    user = User.objects.create_user(
        username, email=f"{username}@greenloop.id", password="pw12345!", **extra
    )
    UserProfile.objects.filter(user=user).update(role=role)
    if role == "courier" and courier_approved is not None:
        CourierProfile.objects.create(user=user, is_approved=courier_approved)
    return user


def make_approved_courier(username="kurir", **extra):
    """Buat kurir yang sudah lolos middleware persetujuan admin."""
    return make_user(username, courier_approved=True, **extra)