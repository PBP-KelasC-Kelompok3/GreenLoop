from django.db import models
from django.contrib.auth.models import User
import uuid


class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)
    price_b2c = models.IntegerField(help_text="Harga Konsumen Publik (B2C)", default=10000)
    price_b2b = models.IntegerField(help_text="Harga Mitra (B2B)", default=7500)
    stock = models.IntegerField(default=0)
    weight_grams = models.PositiveIntegerField(default=500, help_text="Berat satuan untuk kalkulasi ongkir")

    def __str__(self):
        return self.name


class Order(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Menunggu Pembayaran'),
        ('PAID', 'Dibayar - Sedang Diproses'),
        ('PROCESSING', 'Sedang Disiapkan'),
        ('SHIPPED', 'Dalam Pengiriman'),
        ('DELIVERED', 'Terkirim'),
        ('CANCELLED', 'Dibatalkan'),
    )

    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Menunggu Pembayaran'
        PAID = 'PAID', 'Lunas'
        FAILED = 'FAILED', 'Gagal / Kedaluwarsa'
        REFUNDED = 'REFUNDED', 'Dikembalikan'

    order_id = models.CharField(max_length=100, unique=True, default=uuid.uuid4)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    subtotal = models.PositiveIntegerField(default=0)
    shipping_cost = models.PositiveIntegerField(default=0)
    goods_discount = models.PositiveIntegerField(default=0)
    shipping_discount = models.PositiveIntegerField(default=0)
    user_voucher = models.ForeignKey(
        'waste_reward.UserVoucher',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='soap_orders',
    )
    total_amount = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    payment_status = models.CharField(max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    recipient_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=25, blank=True)
    shipping_address = models.TextField(blank=True)
    destination_id = models.CharField(max_length=30, blank=True)
    destination_label = models.CharField(max_length=200, blank=True)
    courier_code = models.CharField(max_length=30, blank=True)
    courier_name = models.CharField(max_length=60, blank=True)
    courier_service = models.CharField(max_length=80, blank=True)
    shipping_eta = models.CharField(max_length=80, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    snap_token = models.CharField(max_length=255, blank=True)
    stock_reserved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.order_id} - {self.user.username} - {self.status}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=255)
    unit_price = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField()

    @property
    def line_total(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"