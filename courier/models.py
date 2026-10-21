from django.conf import settings
from django.db import models


class CourierProfile(models.Model):
    """Data tambahan khusus kurir (satu kurir = satu profil)."""

    class VehicleType(models.TextChoices):
        PICKUP_BAK = "pickup_bak", "Pickup Bak"
        MOTOR_BOX = "motor_box", "Motor Box"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="courierprofile",
    )
    plate_number = models.CharField(max_length=15, blank=True)
    vehicle_type = models.CharField(
        max_length=20,
        choices=VehicleType.choices,
        default=VehicleType.PICKUP_BAK,
    )
    is_on_duty = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} ({self.plate_number or '-'})"