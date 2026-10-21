import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm

from .models import CourierProfile

User = get_user_model()

# Contoh valid: B 1234 KZT, D 12 AB, B1234KZT
PLATE_RE = re.compile(r"^[A-Z]{1,2}\s?\d{1,4}\s?[A-Z]{0,3}$")


class CourierProfileForm(forms.Form):
    full_name = forms.CharField(
        max_length=150,
        error_messages={"required": "Nama lengkap wajib diisi."},
    )
    email = forms.EmailField(
        error_messages={
            "required": "Email wajib diisi.",
            "invalid": "Format email tidak valid.",
        },
    )
    plate_number = forms.CharField(
        max_length=15,
        error_messages={"required": "Plat nomor wajib diisi."},
    )
    vehicle_type = forms.ChoiceField(
        choices=CourierProfile.VehicleType.choices,
        error_messages={
            "required": "Jenis armada wajib dipilih.",
            "invalid_choice": "Pilih jenis armada yang tersedia.",
        },
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_full_name(self):
        return " ".join(self.cleaned_data["full_name"].split())

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        taken = User.objects.filter(email__iexact=email).exclude(pk=self.user.pk)
        if taken.exists():
            raise forms.ValidationError("Email sudah dipakai akun lain.")
        return email

    def clean_plate_number(self):
        plate = " ".join(self.cleaned_data["plate_number"].upper().split())
        if not PLATE_RE.match(plate):
            raise forms.ValidationError(
                "Format plat nomor tidak valid. Contoh: B 1234 KZT."
            )
        return plate

    def save(self):
        data = self.cleaned_data

        self.user.first_name = data["full_name"]
        self.user.last_name = ""
        self.user.email = data["email"]
        self.user.save(update_fields=["first_name", "last_name", "email"])

        profile, _ = CourierProfile.objects.get_or_create(user=self.user)
        profile.plate_number = data["plate_number"]
        profile.vehicle_type = data["vehicle_type"]
        profile.save(update_fields=["plate_number", "vehicle_type"])
        return profile


class CourierPasswordForm(PasswordChangeForm):
    error_messages = {
        "password_mismatch": "Kata sandi baru dan konfirmasi tidak sama.",
        "password_incorrect": "Kata sandi saat ini salah.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.error_messages["required"] = "Wajib diisi."


def errors_to_dict(form):
    """{'field': ['pesan', ...]} supaya mudah dibaca JavaScript."""
    return {
        field: [item["message"] for item in items]
        for field, items in form.errors.get_json_data().items()
    }