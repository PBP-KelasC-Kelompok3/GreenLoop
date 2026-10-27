from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

# Tarif Waste Points per kilogram (contoh: 58,6 kg x 5 = 293 poin)
POINTS_PER_KG = 5


def points_for(weight_kg):
    """Menghitung Waste Points dari berat, dibulatkan ke bilangan bulat."""
    return int((Decimal(weight_kg) * POINTS_PER_KG).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class CourierProfile(models.Model):
    """Data tambahan khusus kurir (satu kurir = satu profil)."""

    # Pilihan jenis armada
    class VehicleType(models.TextChoices):
        PICKUP_BAK = "pickup_bak", "Pickup Bak"
        MOTOR_BOX = "motor_box", "Motor Box"

    # Satu user hanya punya satu profil kurir;
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
    is_on_duty = models.BooleanField(default=False)  # Status "Sedang Bertugas"

    def __str__(self):
        return f"{self.user.username} ({self.plate_number or '-'})"


class WeightLog(models.Model):
    """Satu catatan timbangan hasil penjemputan. Dikelola kurir (CRUD)."""

    # Pemilik catatan; dipakai untuk memastikan kurir hanya melihat datanya sendiri
    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="weight_logs",
    )
    partner_name = models.CharField("Mitra / lokasi", max_length=120)
    collected_at = models.DateField("Tanggal")
    # Berat dengan satu angka di belakang koma, antara 0,1 sampai 5.000 kg
    weight_kg = models.DecimalField(
        "Berat bersih (kg)",
        max_digits=7,
        decimal_places=1,
        validators=[MinValueValidator(Decimal("0.1")), MaxValueValidator(Decimal("5000"))],
    )
    notes = models.CharField("Catatan", max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Data terbaru tampil paling atas
    class Meta:
        ordering = ["-collected_at", "-id"]

    def __str__(self):
        return f"{self.partner_name} {self.weight_kg} kg ({self.collected_at})"

    # Poin tidak disimpan di database, selalu dihitung dari berat
    @property
    def points(self):
        return points_for(self.weight_kg)


class CollectionPoint(models.Model):
    """Titik jemput (mitra seperti kafe, restoran, hotel) yang menjadi data awal halaman Rute Hari Ini.

    Sementara dipakai sebelum model Pickup ada. Datanya diisi lewat
    `python manage.py seed_points` (diambil dari OpenStreetMap lewat Overpass API).
    """

    code = models.CharField("Kode", max_length=20, unique=True)
    name = models.CharField("Nama", max_length=120)
    category = models.CharField("Jenis", max_length=40)
    address = models.CharField("Alamat", max_length=200)
    # Koordinat asli dari OpenStreetMap, sama dengan yang tergambar di peta
    latitude = models.FloatField()
    longitude = models.FloatField()
    est_kg = models.PositiveSmallIntegerField("Estimasi berat (kg)", default=20)
    vehicle = models.CharField("Armada", max_length=30, default="Motor Box")
    photo_note = models.CharField("Catatan foto", max_length=120, blank=True)
    # Penanda asal data (mis. "node/123456") supaya seed bisa dijalankan berulang tanpa duplikat
    source_id = models.CharField(max_length=40, unique=True, null=True, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"


class PickupRecord(models.Model):
    """Catatan satu penjemputan milik kurir; dibaca halaman Riwayat Pikap.

    Dibuat saat kurir menekan Mulai Perjalanan (status ongoing) dan diperbarui
    saat Selesai Pikap (status done, lengkap dengan berat aktual).
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Dijadwalkan"
        ONGOING = "ongoing", "Dalam Perjalanan"
        DONE = "done", "Selesai"
        CANCELLED = "cancelled", "Dibatalkan"

    courier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pickup_records",
    )
    code = models.CharField("Kode titik", max_length=20)
    date = models.DateField("Tanggal")
    slot = models.CharField("Slot", max_length=20, blank=True)
    partner_name = models.CharField("Mitra", max_length=120)
    area = models.CharField("Area", max_length=200, blank=True)
    est_kg = models.PositiveSmallIntegerField("Estimasi (kg)", default=0)
    actual_kg = models.DecimalField("Berat aktual (kg)", max_digits=7, decimal_places=1, null=True, blank=True)
    vehicle = models.CharField("Armada", max_length=30, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ONGOING)
    note = models.CharField("Catatan", max_length=200, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        # Satu titik hanya tercatat sekali per hari untuk satu kurir
        constraints = [
            models.UniqueConstraint(fields=["courier", "date", "code"], name="unique_pickup_per_day"),
        ]

    def __str__(self):
        return f"{self.code} {self.partner_name} ({self.date}, {self.status})"