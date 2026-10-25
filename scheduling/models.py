from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator


class PickupSchedule(models.Model):

    STATUS_CHOICES = [
        ('PENDING', 'Pending Verification'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('SCHEDULED', 'Scheduled'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    WASTE_TYPE_CHOICES = [
        ('ORGANIC_FOOD', 'Sisa Makanan / Dapur'),
        ('COFFEE_GROUNDS', 'Ampas Kopi'),
        ('FRUIT_VEG', 'Sisa Buah & Sayur'),
        ('MIXED_ORGANIC', 'Organik Campuran'),
    ]

    ARMADA_CHOICES = [
        ('Motor Box', 'Motor Box'),
        ('Pickup Bak', 'Pickup Bak'),
        ('Truk Kecil', 'Truk Kecil'),
    ]

    mitra = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='pickup_schedules'
    )

    waste_type = models.CharField(
        max_length=30,
        choices=WASTE_TYPE_CHOICES,
        default='MIXED_ORGANIC'
    )

    estimated_weight = models.FloatField(
        validators=[MinValueValidator(0.01)],
        help_text="Berat limbah dalam kg"
    )

    pickup_date = models.DateField()

    pickup_time_slot = models.CharField(max_length=50)

    # Pilihan Armada Pengangkut
    armada = models.CharField(
        max_length=50, 
        choices=ARMADA_CHOICES, 
        default='Pickup Bak',
        verbose_name="Jenis Armada"
    )

    waste_photo = models.ImageField(
        upload_to='pickup_photos/',
        blank=True,
        null=True,
        help_text="Foto kondisi sampah organik"
    )

    notes = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    
    # Berat Aktual dari kurir (cukup ditulis sekali saja dengan max_length & max_digits yang benar)
    actual_weight = models.DecimalField(
        max_digits=6, 
        decimal_places=2, 
        null=True, 
        blank=True, 
        verbose_name="Berat Aktual (kg)"
    )

    points = models.IntegerField(default=0, verbose_name="Poin Diperoleh")

    # Kolom untuk file sertifikat milestone
    certificate = models.FileField(
        upload_to='certificates/',
        blank=True,
        null=True,
        verbose_name="Sertifikat Kontribusi"
    )

    class Meta:
        ordering = ['-pickup_date', '-created_at']

    def __str__(self):
        return f"{self.mitra.username} - {self.pickup_date} ({self.get_status_display()})"

class MitraProfile(models.Model):
    JENIS_USAHA_CHOICES = [
        ('Kafe', 'Kafe'),
        ('Restoran', 'Restoran'),
        ('Hotel', 'Hotel'),
        ('Katering', 'Katering'),
        ('Lainnya', 'Lainnya'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    business_name = models.CharField(max_length=150, verbose_name="Nama Usaha", blank=True, null=True)
    business_type = models.CharField(max_length=50, choices=JENIS_USAHA_CHOICES, blank=True, null=True)
    pic_name = models.CharField(max_length=100, verbose_name="Nama Penanggung Jawab", blank=True, null=True)
    phone_number = models.CharField(max_length=20, verbose_name="No. WhatsApp", blank=True, null=True)
    operational_hours = models.CharField(max_length=50, verbose_name="Jam Operasional", blank=True, null=True)
    
    # Wilayah Penjemputan (Dapat diisi dari Form atau Autocomplete API)
    provinsi = models.CharField(max_length=100, blank=True, null=True)
    kota = models.CharField(max_length=100, blank=True, null=True)
    kecamatan = models.CharField(max_length=100, blank=True, null=True)
    kelurahan = models.CharField(max_length=100, blank=True, null=True)
    address_detail = models.TextField(verbose_name="Alamat Detail", blank=True, null=True)
    
    # Titik Koordinat dari Google Maps API (Places Autocomplete / Pin Drag)
    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Profil {self.business_name or self.user.username}"