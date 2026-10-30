from django import forms

from .models import RewardVoucher


class RewardVoucherForm(forms.ModelForm):
    """Validated staff form for creating and updating the shared voucher catalog."""

    class Meta:
        model = RewardVoucher
        fields = (
            'code', 'title', 'kind', 'value_label', 'points_cost',
            'description', 'valid_days', 'is_active', 'sort_order',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_code(self):
        return self.cleaned_data['code'].strip().lower()

    def clean_title(self):
        value = self.cleaned_data['title'].strip()
        if not value:
            raise forms.ValidationError('Nama voucher wajib diisi.')
        return value

    def clean_value_label(self):
        value = self.cleaned_data['value_label'].strip()
        if not value:
            raise forms.ValidationError('Nilai voucher wajib diisi.')
        return value

    def clean_points_cost(self):
        value = self.cleaned_data['points_cost']
        if value < 1:
            raise forms.ValidationError('Biaya poin harus lebih dari 0.')
        return value

    def clean_valid_days(self):
        value = self.cleaned_data['valid_days']
        if value < 1:
            raise forms.ValidationError('Masa berlaku harus minimal 1 hari.')
        return value
