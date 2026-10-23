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

    class Meta:
        ordering = ['-pickup_date', '-created_at']

    def __str__(self):
        return f"{self.mitra.username} - {self.pickup_date} ({self.get_status_display()})"

    actual_weight = models.DecimalField(max_length=6, decimal_places=2, max_digits=6, null=True, blank=True, verbose_name="Berat Aktual (kg)")