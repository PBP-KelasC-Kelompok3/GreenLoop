from django import forms
from .models import Product

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'price_b2c', 'price_b2b', 'stock']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Nama Produk'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 2, 'placeholder': 'Deskripsi produk...'}),
            'price_b2c': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Contoh: 15000'}),
            'price_b2b': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Contoh: 12000'}),
            'stock': forms.NumberInput(attrs={'class': 'form-input', 'placeholder': 'Contoh: 50'}),
        }