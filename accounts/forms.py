from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
import re

from .models import UserProfile


PHONE_RE = r"^(?:\+62|62|0)8\d{7,12}$"
PLATE_RE = re.compile(r"^[A-Z]{1,2}\s?\d{1,4}\s?[A-Z]{0,3}$")

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

            if cleaned.get('kota', '').strip().casefold() not in ('depok', 'kota depok'):
                self.add_error('kota', 'Layanan mitra saat ini hanya tersedia di Kota Depok.')

            phone = cleaned.get('phone_number', '')
            phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')

            if phone and not re.match(PHONE_RE, phone):
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
            if not cleaned['plate_number']:
                self.add_error('plate_number', 'Plat nomor wajib diisi untuk akun kurir.')
            elif not PLATE_RE.fullmatch(cleaned['plate_number']):
                self.add_error('plate_number', 'Format plat nomor tidak valid. Contoh: B 1234 KZT.')

            if not cleaned.get('vehicle_type'):
                self.add_error('vehicle_type', 'Jenis armada wajib dipilih untuk akun kurir.')

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
        Simpan data awal pendaftaran ke model profil sesuai peran.
        """
        profile = getattr(user, 'userprofile', None)

        if profile:
            profile.role = self.cleaned_data.get('role')
            profile.save(update_fields=['role'])

        role = self.cleaned_data.get('role')

        if role == 'mitra':
            from scheduling.models import MitraProfile

            business_type = {
                'cafe': 'Kafe / Coffee Shop',
                'restaurant': 'Restoran',
                'hotel': 'Hotel',
            }.get(self.cleaned_data.get('business_type', ''), self.cleaned_data.get('business_type', ''))

            MitraProfile.objects.update_or_create(
                user=user,
                defaults={
                    'business_name': self.cleaned_data.get('business_name', '').strip(),
                    'business_type': business_type,
                    'pic_name': self.cleaned_data.get('pic_name', '').strip(),
                    'phone_number': self.cleaned_data.get('phone_number', '').strip(),
                    'provinsi': self.cleaned_data.get('provinsi', '').strip(),
                    'kota': self.cleaned_data.get('kota', '').strip(),
                    'kecamatan': self.cleaned_data.get('kecamatan', '').strip(),
                    'kelurahan': self.cleaned_data.get('kelurahan', '').strip(),
                    'address_detail': self.cleaned_data.get('address_detail', '').strip(),
                },
            )
        elif role == 'courier':
            from courier.models import CourierProfile

            vehicle_type = {
                'motor': CourierProfile.VehicleType.MOTOR_BOX,
                'mobil': CourierProfile.VehicleType.PICKUP_BAK,
            }.get(self.cleaned_data.get('vehicle_type'), CourierProfile.VehicleType.PICKUP_BAK)

            CourierProfile.objects.update_or_create(
                user=user,
                defaults={
                    'plate_number': self.cleaned_data['plate_number'],
                    'vehicle_type': vehicle_type,
                },
            )
            full_name = ' '.join((self.cleaned_data.get('full_name') or '').split())
            if full_name:
                user.first_name = full_name
                user.last_name = ''
                user.save(update_fields=['first_name', 'last_name'])
