from django import forms
from .models import Product

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'price_b2c', 'price_b2b', 'stock', 'weight_grams']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nama Produk'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 2, 'placeholder': 'Deskripsi produk...'}),
            'price_b2c': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Contoh: 15000'}),
            'price_b2b': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Contoh: 12000'}),
            'stock': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Contoh: 50'}),
            'weight_grams': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Berat per produk (gram)'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        for field in ('price_b2c', 'price_b2b', 'stock'):
            value = cleaned_data.get(field)
            if value is not None and value < 0:
                self.add_error(field, 'Nilai tidak boleh kurang dari 0.')
        weight = cleaned_data.get('weight_grams')
        if weight is not None and weight <= 0:
            self.add_error('weight_grams', 'Berat produk harus lebih dari 0 gram.')
        return cleaned_data
