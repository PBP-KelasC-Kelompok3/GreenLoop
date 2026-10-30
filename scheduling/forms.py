from django import forms
from django.core.exceptions import ValidationError
from .models import MitraProfile, PickupSchedule
from .schedule_rules import PICKUP_TIME_SLOTS, validate_pickup_window


class MitraProfileForm(forms.ModelForm):
    class Meta:
        model = MitraProfile
        fields = (
            'business_name', 'business_type', 'pic_name', 'phone_number',
            'operational_hours', 'provinsi', 'kota', 'kecamatan',
            'kelurahan', 'address_detail', 'courier_notes',
        )
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Nama usaha/toko'}),
            'business_type': forms.Select(attrs={'class': 'form-select rounded-3'}),
            'pic_name': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Nama PIC'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': '08xxxxxxxxxx'}),
            'operational_hours': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Contoh: 07.00–22.00 WIB'}),
            'provinsi': forms.TextInput(attrs={'class': 'form-control rounded-3'}),
            'kota': forms.TextInput(attrs={'class': 'form-control rounded-3'}),
            'kecamatan': forms.TextInput(attrs={'class': 'form-control rounded-3'}),
            'kelurahan': forms.TextInput(attrs={'class': 'form-control rounded-3'}),
            'address_detail': forms.Textarea(attrs={'class': 'form-control rounded-3', 'rows': 3}),
            'courier_notes': forms.Textarea(attrs={'class': 'form-control rounded-3', 'rows': 3}),
        }

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '')
        if phone and not all(char.isdigit() or char in '+-() ' for char in phone):
            raise forms.ValidationError('Nomor telepon hanya boleh berisi angka dan karakter + - ( ).')
        return phone

class PickupScheduleForm(forms.ModelForm):
    class Meta:
        model = PickupSchedule
        fields = ['waste_type', 'estimated_weight', 'pickup_date', 'pickup_time_slot', 'armada' , 'waste_photo', 'notes']
        widgets = {
            'waste_type': forms.Select(attrs={'class': 'form-select'}),
            'estimated_weight': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Masukkan berat dalam kg (maksimal 120 kg)',
                'step': '0.1',
                'min': '0.1',
                'max': '120',
            }),
            'pickup_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'pickup_time_slot': forms.Select(
                choices=PICKUP_TIME_SLOTS,
                attrs={'class': 'form-select'},
            ),
            'waste_photo': forms.FileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Catatan lokasi atau instruksi khusus...'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        pickup_date = cleaned_data.get('pickup_date')
        time_slot = cleaned_data.get('pickup_time_slot')
        if pickup_date and time_slot:
            try:
                validate_pickup_window(pickup_date, time_slot)
            except ValidationError as error:
                self.add_error('pickup_time_slot', error)
        return cleaned_data
