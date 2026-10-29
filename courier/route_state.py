"""Titik rute dibentuk dari pengajuan PickupSchedule yang ditugaskan ke kurir."""
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal


from .maps import STATUS_APPROVED, STATUS_DONE, STATUS_ON_THE_WAY
from .utils import MONTHS_ID

DAYS_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


@dataclass
class Stop:
    pk: int
    code: str
    name: str
    address: str
    slot_start: time
    slot_end: time
    est_kg: int
    vehicle: str
    latitude: float
    longitude: float
    photo_note: str
    status: str = STATUS_APPROVED
    finished_at: datetime = None
    actual_kg: Decimal = None

    @property
    def slot_text(self):
        return f"{self.slot_start:%H.%M}–{self.slot_end:%H.%M}"


def format_day_date(value):
    """date(2026, 9, 29) -> 'Selasa, 29 Sep 2026'."""
    return f"{DAYS_ID[value.weekday()]}, {value.day} {MONTHS_ID[value.month - 1]} {value.year}"


# Muatan maksimal armada kurir per penjemputan (kg), sesuai CourierProfile.vehicle_type.
# Estimasi berat di setiap titik disesuaikan dengan armada kurir yang sedang bertugas.
VEHICLE_CAPACITY_KG = {"Motor Box": 5, "Pickup Bak": 10}
LARGEST_CAPACITY_KG = max(VEHICLE_CAPACITY_KG.values())

def estimate_for(base_kg, vehicle):
    """Estimasi berat untuk armada kurir.

    Data titik menyimpan estimasi untuk armada terbesar (1-10 kg). Untuk armada yang lebih kecil
    angkanya diskalakan, jadi motor mendapat 1-5 kg dan pickup 1-10 kg, dan tidak pernah melebihi muatannya.
    """
    cap = VEHICLE_CAPACITY_KG.get(vehicle, LARGEST_CAPACITY_KG)
    # Dibulatkan setengah ke atas (round() Python membulatkan 2,5 ke 2, itu tidak diinginkan)
    scaled = (base_kg * cap * 2 + LARGEST_CAPACITY_KG) // (LARGEST_CAPACITY_KG * 2)
    return max(1, min(cap, scaled))


def _today_stops(user, today, vehicle=None):
    """Pickup hari ini yang memang ditugaskan kepada kurir ini."""
    from scheduling.models import PickupSchedule
    from .models import PickupRecord

    pickups = list(PickupSchedule.objects.filter(
        courier=user,
        pickup_date=today,
        status__in=("SCHEDULED", "IN_PROGRESS", "COMPLETED"),
    ).select_related("mitra").order_by("pickup_time_slot", "pk"))
    from scheduling.models import MitraProfile
    profiles = {
        profile.user_id: profile
        for profile in MitraProfile.objects.filter(user_id__in=[p.mitra_id for p in pickups])
    }
    records = {
        record.pickup_schedule_id: record
        for record in PickupRecord.objects.filter(
            pickup_schedule__in=pickups, courier=user,
        )
    }
    stops = []
    for pickup in pickups:
        profile = profiles.get(pickup.mitra_id)
        if not profile or profile.latitude is None or profile.longitude is None:
            continue
        record = records.get(pickup.pk)
        slot = pickup.pickup_time_slot.replace("–", "-").replace(" WIB", "").split("-")
        try:
            start_hour, start_minute = map(int, slot[0].strip().split(":")[:2])
            end_hour, end_minute = map(int, slot[1].strip().split(":")[:2])
            start = time(start_hour, start_minute)
            end = time(end_hour, end_minute)
        except (IndexError, ValueError):
            start, end = time(8, 0), time(10, 0)
        address = ", ".join(filter(None, (
            profile.address_detail, profile.kelurahan, profile.kecamatan,
            profile.kota, profile.provinsi,
        )))
        if not address:
            address = pickup.mitra.username
        has_started = bool(
            pickup.status == "IN_PROGRESS"
            and record
            and record.status == PickupRecord.Status.ONGOING
        )
        status = STATUS_DONE if pickup.status == "COMPLETED" else (
            STATUS_ON_THE_WAY if has_started else STATUS_APPROVED
        )
        stops.append(Stop(
            pickup.pk, f"PK-{pickup.pk:04d}",
            profile.business_name or pickup.mitra.username, address,
            start, end, max(1, int(round(pickup.estimated_weight))),
            vehicle or pickup.armada, profile.latitude, profile.longitude,
            pickup.notes or "", status=status,
            finished_at=record.finished_at if record else None,
            actual_kg=pickup.actual_weight,
        ))
    return stops


def get_today_stops(user, today, vehicle=None):
    """Rute dan status aktual dari pengajuan pickup yang ditugaskan."""
    return _today_stops(user, today, vehicle)
