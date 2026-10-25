"""Titik jemput hari ini dan status pengerjaannya.

Sementara (sebelum model Pickup ada): titik diambil dari model CollectionPoint, dan
statusnya disimpan di sesi login kurir. Objek Stop sengaja memakai nama atribut yang sama
dengan yang dibaca maps.build_plan (pk, status, slot_start, finished_at,
latitude, longitude), jadi nanti cukup diganti dengan query ke model Pickup.
"""
import random
from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal


from .maps import STATUS_APPROVED, STATUS_DONE, STATUS_ON_THE_WAY, haversine_m
from .utils import MONTHS_ID

SESSION_KEY = "route_state"
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
    """date(2026, 9, 29) -> 'Selasa, 29 Sep'."""
    return f"{DAYS_ID[value.weekday()]}, {value.day} {MONTHS_ID[value.month - 1]}"


# Muatan maksimal armada kurir per penjemputan (kg), sesuai CourierProfile.vehicle_type.
# Estimasi berat di setiap titik disesuaikan dengan armada kurir yang sedang bertugas.
VEHICLE_CAPACITY_KG = {"Motor Box": 5, "Pickup Bak": 10}
LARGEST_CAPACITY_KG = max(VEHICLE_CAPACITY_KG.values())

STOPS_PER_DAY = 5          # jumlah titik jemput yang dijadwalkan tiap hari
FIRST_SLOT_MINUTES = 8 * 60  # titik pertama mulai pukul 08.00
SLOT_STEP = 75             # jarak mulai antar titik (menit)
SLOT_LENGTH = 120          # lebar jendela jemput (menit)


def _slot(index):
    start = FIRST_SLOT_MINUTES + index * SLOT_STEP
    end = start + SLOT_LENGTH
    return time(start // 60, start % 60), time(end // 60 % 24, end % 60)


def estimate_for(base_kg, vehicle):
    """Estimasi berat untuk armada kurir.

    Data titik menyimpan estimasi untuk armada terbesar (1-10 kg). Untuk armada yang lebih kecil
    angkanya diskalakan, jadi motor mendapat 1-5 kg dan pickup 1-10 kg, dan tidak pernah melebihi muatannya.
    """
    cap = VEHICLE_CAPACITY_KG.get(vehicle, LARGEST_CAPACITY_KG)
    # Dibulatkan setengah ke atas (round() Python membulatkan 2,5 ke 2, itu tidak diinginkan)
    scaled = (base_kg * cap * 2 + LARGEST_CAPACITY_KG) // (LARGEST_CAPACITY_KG * 2)
    return max(1, min(cap, scaled))


def _today_stops(today, vehicle=None):
    """Memilih titik jemput hari ini dari data CollectionPoint, dikumpulkan di satu daerah.

    Satu titik pusat dipilih acak dari tanggal (jadi tetap sama sepanjang hari dan untuk semua
    kurir), lalu diambil titik-titik terdekat darinya. Hasilnya rute yang rapat, tidak
    membentang ke ujung-ujung Depok. Kosong bila data belum di-seed.
    """
    from .models import CollectionPoint

    points = list(CollectionPoint.objects.order_by("pk"))
    if not points:
        return []
    center = random.Random(today.toordinal()).choice(points)
    here = (center.latitude, center.longitude)
    nearest = sorted(points, key=lambda p: (haversine_m(here, (p.latitude, p.longitude)), p.pk))
    stops = []
    for index, point in enumerate(nearest[:STOPS_PER_DAY]):
        start, end = _slot(index)
        stops.append(Stop(
            point.pk, point.code, point.name, point.address, start, end,
            estimate_for(point.est_kg, vehicle), vehicle or "",
            point.latitude, point.longitude, point.photo_note,
        ))
    return stops


def _load_state(session, today):
    state = session.get(SESSION_KEY)
    # Status hanya berlaku untuk hari yang sama; hari baru mulai dari data awal
    if not state or state.get("date") != today.isoformat():
        return {"date": today.isoformat(), "stops": {}}
    return state


def get_today_stops(session, today, vehicle=None):
    """Titik jemput hari ini, dengan status terbaru dari sesi."""
    overlay = _load_state(session, today)["stops"]
    stops = _today_stops(today, vehicle)
    for stop in stops:
        saved = overlay.get(str(stop.pk))
        if not saved:
            continue
        stop.status = saved["status"]
        stop.finished_at = (
            datetime.fromisoformat(saved["finished_at"]) if saved.get("finished_at") else None
        )
        stop.actual_kg = Decimal(saved["actual_kg"]) if saved.get("actual_kg") else None
    return stops


def set_stop_state(session, today, pk, status, finished_at=None, actual_kg=None):
    """Menyimpan status satu titik ke sesi."""
    state = _load_state(session, today)
    state["stops"][str(pk)] = {
        "status": status,
        "finished_at": finished_at.isoformat() if finished_at else None,
        "actual_kg": str(actual_kg) if actual_kg is not None else None,
    }
    session[SESSION_KEY] = state
    session.modified = True


def reset_state(session):
    """Mengembalikan semua titik ke data awal (untuk mencoba ulang demo)."""
    session.pop(SESSION_KEY, None)