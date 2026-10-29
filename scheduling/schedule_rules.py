"""Aturan jadwal penjemputan yang dipakai form dan validasi server."""
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone


PICKUP_TIME_SLOTS = (
    ("08:00 - 10:00 WIB", "08:00 - 10:00 WIB"),
    ("10:00 - 12:00 WIB", "10:00 - 12:00 WIB"),
    ("13:00 - 15:00 WIB", "13:00 - 15:00 WIB"),
    ("15:00 - 17:00 WIB", "15:00 - 17:00 WIB"),
)
BOOKING_LEAD_TIME = timedelta(hours=1)


def validate_pickup_window(pickup_date, time_slot, *, now=None):
    """Tolak jadwal lampau atau yang diminta kurang dari 1 jam sebelumnya."""
    if not pickup_date or not time_slot:
        raise ValidationError("Pilih tanggal dan slot waktu penjemputan.")

    start_text = time_slot.split(" - ", 1)[0]
    try:
        start_time = datetime.strptime(start_text, "%H:%M").time()
    except ValueError as exc:
        raise ValidationError("Slot waktu penjemputan tidak valid.") from exc

    now = now or timezone.localtime()
    if pickup_date < timezone.localdate(now):
        raise ValidationError("Tanggal penjemputan tidak boleh sudah lewat.")

    slot_start = timezone.make_aware(
        datetime.combine(pickup_date, start_time),
        timezone.get_current_timezone(),
    )
    if slot_start < now + BOOKING_LEAD_TIME:
        raise ValidationError(
            "Jadwal harus dipilih minimal 1 jam sebelum slot dimulai."
        )
