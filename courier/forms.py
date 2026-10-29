import re
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm
from django.utils import timezone

from .models import CourierProfile, WeightLog

User = get_user_model()

# Pola plat nomor Indonesia. Contoh valid: B 1234 KZT, D 12 AB, B1234KZT
PLATE_RE = re.compile(r"^[A-Z]{1,2}\s?\d{1,4}\s?[A-Z]{0,3}$")


class CourierProfileForm(forms.Form):
    """Form Edit Profil. Berupa Form biasa karena datanya tersebar di User dan CourierProfile."""

    # Isian beserta pesan kesalahan berbahasa Indonesia
    full_name = forms.CharField(
        max_length=150,
        error_messages={"required": "Nama lengkap wajib diisi."},
    )
    username = forms.CharField(
        required=False,
        max_length=150,
        validators=User._meta.get_field("username").validators,
        error_messages={"max_length": "Username maksimal 150 karakter."},
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
        self.user = user  # Dipakai untuk memeriksa email milik orang lain

    def clean_full_name(self):
        # Merapikan spasi berlebih, contoh: "  Budi   Santoso " -> "Budi Santoso"
        return " ".join(self.cleaned_data["full_name"].split())

    def clean_username(self):
        username = (self.cleaned_data.get("username") or self.user.username).strip()
        taken = User.objects.filter(username__iexact=username).exclude(pk=self.user.pk)
        if taken.exists():
            raise forms.ValidationError("Username sudah dipakai akun lain.")
        return username

    def clean_email(self):
        # Email disimpan huruf kecil dan tidak boleh sama dengan akun lain
        email = self.cleaned_data["email"].strip().lower()
        taken = User.objects.filter(email__iexact=email).exclude(pk=self.user.pk)
        if taken.exists():
            raise forms.ValidationError("Email sudah dipakai akun lain.")
        return email

    def clean_plate_number(self):
        # Plat nomor dijadikan huruf besar dan harus sesuai pola
        plate = " ".join(self.cleaned_data["plate_number"].upper().split())
        if not PLATE_RE.match(plate):
            raise forms.ValidationError(
                "Format plat nomor tidak valid. Contoh: B 1234 KZT."
            )
        return plate

    def save(self):
        data = self.cleaned_data

        # Menyimpan nama dan email ke tabel User
        self.user.first_name = data["full_name"]
        self.user.last_name = ""
        self.user.username = data["username"]
        self.user.email = data["email"]
        self.user.save(update_fields=["first_name", "last_name", "username", "email"])

        # Menyimpan plat nomor dan armada ke CourierProfile (dibuat bila belum ada)
        profile, _ = CourierProfile.objects.get_or_create(user=self.user)
        profile.plate_number = data["plate_number"]
        profile.vehicle_type = data["vehicle_type"]
        profile.save(update_fields=["plate_number", "vehicle_type"])
        return profile


class CourierPhotoForm(forms.Form):
    profile_photo = forms.ImageField(required=True)


class CourierPasswordForm(PasswordChangeForm):
    """Form Ganti Kata Sandi bawaan Django dengan pesan berbahasa Indonesia."""

    error_messages = {
        "password_mismatch": "Kata sandi baru dan konfirmasi tidak sama.",
        "password_incorrect": "Kata sandi saat ini salah.",
    }
 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.error_messages["required"] = "Wajib diisi."


class CommaDecimalField(forms.DecimalField):
    """Menerima '12,5' maupun '12.5'."""

    def to_python(self, value):
        # Koma diganti titik sebelum diproses sebagai angka
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        return super().to_python(value)


class WeightLogForm(forms.ModelForm):
    """Form tambah dan ubah catatan timbangan."""

    # Berat memakai field sendiri agar koma desimal diterima dan pesan errornya berbahasa Indonesia
    weight_kg = CommaDecimalField(
        max_digits=7,
        decimal_places=1,
        min_value=Decimal("0.1"),
        max_value=Decimal("5000"),
        error_messages={
            "required": "Berat wajib diisi.",
            "invalid": "Masukkan angka yang valid, contoh: 35,2.",
            "min_value": "Berat minimal 0,1 kg.",
            "max_value": "Berat maksimal 5.000 kg.",
            "max_decimal_places": "Maksimal 1 angka di belakang koma.",
            "max_digits": "Angka terlalu besar.",
        },
    )

    class Meta:
        model = WeightLog
        fields = ["partner_name", "collected_at", "weight_kg", "notes"]
        error_messages = {
            "partner_name": {"required": "Mitra / lokasi wajib diisi."},
            "collected_at": {
                "required": "Tanggal wajib diisi.",
                "invalid": "Format tanggal tidak valid.",
            },
        }

    def clean_partner_name(self):
        # Merapikan spasi dan menolak nama yang hanya berisi spasi
        name = " ".join(self.cleaned_data["partner_name"].split())
        if not name:
            raise forms.ValidationError("Mitra / lokasi wajib diisi.")
        return name

    def clean_collected_at(self):
        # Tanggal timbangan tidak boleh di masa depan
        day = self.cleaned_data["collected_at"]
        if day > timezone.localdate():
            raise forms.ValidationError("Tanggal tidak boleh di masa depan.")
        return day

    def clean_notes(self):
        return " ".join(self.cleaned_data["notes"].split())


def errors_to_dict(form):
    """{'field': ['pesan', ...]} supaya mudah dibaca JavaScript."""
    return {
        field: [item["message"] for item in items]
        for field, items in form.errors.get_json_data().items()
    }
