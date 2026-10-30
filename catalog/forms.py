from django import forms
from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'image', 'price_b2c', 'price_b2b', 'stock', 'weight_grams']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nama Produk'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 2, 'placeholder': 'Deskripsi produk...'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-input', 'accept': 'image/*'}),
            'price_b2c': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Contoh: 15000'}),
            'price_b2b': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Contoh: 12000'}),
            'stock': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Contoh: 50'}),
            'weight_grams': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Contoh: 500'}),
        }


class CheckoutForm(forms.Form):
    recipient_name = forms.CharField(max_length=150, label='Nama penerima')
    phone = forms.CharField(max_length=25, label='Nomor WhatsApp')
    shipping_address = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), label='Alamat lengkap')
    destination_id = forms.CharField(max_length=30, widget=forms.HiddenInput())
    destination_label = forms.CharField(max_length=200, widget=forms.HiddenInput())
    courier_code = forms.CharField(max_length=30, widget=forms.HiddenInput())
    courier_service = forms.CharField(max_length=80, widget=forms.HiddenInput())
    voucher_code = forms.CharField(max_length=16, required=False)
    def clean_destination_id(self):
        value = self.cleaned_data['destination_id']
        if not value.isdigit():
            raise forms.ValidationError('Pilih tujuan pengiriman dari hasil pencarian.')
        return value
