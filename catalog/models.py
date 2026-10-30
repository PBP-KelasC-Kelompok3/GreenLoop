from django.db import models
from django.contrib.auth.models import User
import uuid

class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price_b2c = models.IntegerField(help_text="Harga Konsumen Publik (B2C)", default=10000)
    price_b2b = models.IntegerField(help_text="Harga Mitra (B2B)", default=7500)
    stock = models.IntegerField(default=0)
    weight_grams = models.PositiveIntegerField(default=1000, help_text="Berat produk untuk menghitung ongkir")

    def __str__(self):
        return self.name
        
class Order(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Menunggu Pembayaran'),
        ('PAID', 'Dibayar - Sedang Diproses'),
        ('DELIVERED', 'Terkirim'),
        ('CANCELLED', 'Dibatalkan'),
    )
    
    order_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=255, blank=True, default='')
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.PositiveIntegerField(default=0)
    subtotal = models.PositiveIntegerField(default=0)
    shipping_cost = models.PositiveIntegerField(default=0)
    goods_discount = models.PositiveIntegerField(default=0)
    shipping_discount = models.PositiveIntegerField(default=0)
    recipient_name = models.CharField(max_length=100, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    address = models.TextField(blank=True, default='')
    destination_id = models.CharField(max_length=30, blank=True, default='')
    courier_code = models.CharField(max_length=20, blank=True, default='')
    courier_service = models.CharField(max_length=80, blank=True, default='')
    voucher = models.ForeignKey(
        'waste_reward.UserVoucher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    payment_token = models.CharField(max_length=200, blank=True, default='')
    total_amount = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order_id} - {self.user.username} - {self.status}"

    @property
    def gross_amount(self):
        return self.total_amount

    @property
    def midtrans_order_id(self):
        return self.order_id
