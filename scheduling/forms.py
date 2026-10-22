from django import forms
from .models import PickupSchedule

class PickupScheduleForm(forms.ModelForm):
    class Meta:
        model = PickupSchedule
        fields = ['waste_type', 'estimated_weight', 'pickup_date', 'pickup_time_slot', 'waste_photo', 'notes']
        widgets = {
            'waste_type': forms.Select(attrs={'class': 'form-select'}),
            'estimated_weight': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Masukkan berat dalam kg (contoh: 15.5)', 'step': '0.1'}),
            'pickup_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'pickup_time_slot': forms.Select(choices=[
                ('08:00 - 10:00 WIB', '08:00 - 10:00 WIB'),
                ('10:00 - 12:00 WIB', '10:00 - 12:00 WIB'),
                ('13:00 - 15:00 WIB', '13:00 - 15:00 WIB'),
                ('15:00 - 17:00 WIB', '15:00 - 17:00 WIB'),
            ], attrs={'class': 'form-select'}),
            'waste_photo': forms.FileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Catatan lokasi atau instruksi khusus...'}),
        }