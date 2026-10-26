from django.db import models
from django.contrib.auth.models import User
import uuid

class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price_b2c = models.IntegerField(help_text="Harga Konsumen Publik (B2C)", default=10000)
    price_b2b = models.IntegerField(help_text="Harga Mitra (B2B)", default=7500)
    stock = models.IntegerField(default=0)

    def __str__(self):
        return self.name
        
class Order(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Menunggu Pembayaran'),
        ('PAID', 'Dibayar - Sedang Diproses'),
        ('DELIVERED', 'Terkirim'),
    )
    
    order_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    total_amount = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order_id} - {self.user.username} - {self.status}"