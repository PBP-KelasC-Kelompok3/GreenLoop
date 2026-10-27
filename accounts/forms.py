from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import UserProfile


PHONE_RE = r"^(?:\+62|62|0)8\d{7,12}$"

BUSINESS_TYPE_CHOICES = [
    ('', 'Pilih jenis usaha'),
    ('cafe', 'Kafe'),
    ('restaurant', 'Restoran'),
    ('hotel', 'Hotel'),
]

VEHICLE_TYPE_CHOICES = [
    ('', 'Pilih jenis armada'),
    ('motor', 'Motor'),
    ('mobil', 'Mobil'),
]


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    role = forms.ChoiceField(
        choices=[
            ('consumer', 'Consumer'),
            ('mitra', 'Mitra'),
            ('courier', 'Courier'),
        ],
        widget=forms.RadioSelect,
        label='Daftar sebagai'
    )

    # Mitra fields
    business_name = forms.CharField(
        label='Nama Usaha',
        max_length=150,
        required=False
    )

    business_type = forms.ChoiceField(
        label='Jenis Usaha',
        required=False,
        choices=BUSINESS_TYPE_CHOICES,
    )

    pic_name = forms.CharField(
        label='Nama Penanggung Jawab',
        max_length=100,
        required=False
    )

    phone_number = forms.CharField(
        label='No. WhatsApp',
        max_length=20,
        required=False
    )

    provinsi = forms.CharField(
        label='Provinsi',
        max_length=100,
        required=False
    )

    kota = forms.CharField(
        label='Kota / Kabupaten',
        max_length=100,
        required=False
    )

    kecamatan = forms.CharField(
        label='Kecamatan',
        max_length=100,
        required=False
    )

    kelurahan = forms.CharField(
        label='Kelurahan',
        max_length=100,
        required=False
    )

    address_detail = forms.CharField(
        label='Alamat Lengkap',
        required=False
    )

    # Courier fields
    full_name = forms.CharField(
        label='Nama Lengkap',
        max_length=150,
        required=False
    )

    plate_number = forms.CharField(
        label='Plat Nomor',
        max_length=15,
        required=False
    )

    vehicle_type = forms.ChoiceField(
        label='Jenis Armada',
        required=False,
        choices=VEHICLE_TYPE_CHOICES,
    )

    MITRA_REQUIRED = [
        'business_name',
        'business_type',
        'pic_name',
        'phone_number',
        'provinsi',
        'kota',
        'kecamatan',
        'kelurahan',
        'address_detail',
    ]

    class Meta:
        model = User
        fields = [
            'username',
            'email',
            'password1',
            'password2',
            'role',
        ]

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')

        if role == 'mitra':
            for name in self.MITRA_REQUIRED:
                value = (cleaned.get(name) or '').strip()
                cleaned[name] = value

                if not value:
                    self.add_error(
                        name,
                        'Wajib diisi untuk akun Mitra.'
                    )

            phone = cleaned.get('phone_number', '')
            phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')

            if phone and not __import__('re').match(PHONE_RE, phone):
                self.add_error(
                    'phone_number',
                    'Format nomor WhatsApp tidak valid.'
                )

            cleaned['phone_number'] = phone

        elif role == 'courier':
            cleaned['full_name'] = ' '.join(
                (cleaned.get('full_name') or '').split()
            )

            cleaned['plate_number'] = ' '.join(
                (cleaned.get('plate_number') or '').upper().split()
            )

        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)

        role = self.cleaned_data.get('role')

        if commit:
            user.save()

            # UserProfile otomatis dibuat oleh signal.
            # Di sini kita hanya set role-nya.
            profile = getattr(user, 'userprofile', None)

            if profile:
                profile.role = role
                profile.save(update_fields=['role'])

        return user

    def save_role_profile(self, user):
        """
        Compatibility method untuk code/test lama.

        Data profile Mitra/Courier belum disimpan ke model khusus
        karena source model courier/scheduling tidak tersedia
        pada branch ini.
        """
        profile = getattr(user, 'userprofile', None)

        if profile:
            profile.role = self.cleaned_data.get('role')
            profile.save(update_fields=['role'])