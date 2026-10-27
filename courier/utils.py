# Nama bulan singkat bahasa Indonesia (tidak bergantung pada pengaturan bahasa Django)
MONTHS_ID = [
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]


def get_display_name(user):
    # Memakai nama lengkap; kalau kosong, pakai username
    return (user.get_full_name() or user.username).strip()


def get_initials(user):
    """Inisial untuk avatar: 'Budi Santoso' -> 'BS', 'budi' -> 'BU'."""
    parts = get_display_name(user).split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    return parts[0][:2].upper() if parts else "?"


def format_date_id(value):
    """20 Okt 2026 (nama bulan bahasa Indonesia, tidak bergantung pada setting bahasa)."""
    return f"{value.day} {MONTHS_ID[value.month - 1]} {value.year}"


def build_topbar_sub(profile):
    # Teks kecil di bawah nama pada topbar, contoh: "Kurir · B 1234 KZT"
    if profile.plate_number:
        return f"Kurir · {profile.plate_number}"
    return "Kurir"


def profile_payload(user, profile):
    """Data yang dikirim ke browser setelah profil diubah (dipakai AJAX)."""
    return {
        "display_name": get_display_name(user),
        "initials": get_initials(user),
        "email": user.email,
        "plate_number": profile.plate_number,
        "vehicle_label": profile.get_vehicle_type_display(),
        "topbar_sub": build_topbar_sub(profile),
    }


def get_courier_stats(user):
    # Diimpor di sini (bukan di atas file) untuk menghindari impor melingkar
    from decimal import Decimal

    from .models import WeightLog, points_for

    weights = list(
        WeightLog.objects.filter(courier=user).values_list("weight_kg", flat=True)
    )
    return {
        "pickups_done": len(weights),
        "total_kg": sum(weights, Decimal("0")),
        "points": sum(points_for(w) for w in weights),
    }


# ===================== Riwayat pikap =====================

PICKUP_STATUS = {
    "scheduled": "Dijadwalkan",
    "ongoing": "Dalam Perjalanan",
    "done": "Selesai",
    "cancelled": "Dibatalkan",
}


def get_pickup_history(user):
    """Riwayat pikap milik kurir, diambil dari tabel PickupRecord (terbaru paling atas)."""
    from .models import PickupRecord

    rows = [
        (r.code, r.date.isoformat(), r.slot, r.partner_name, r.area, r.est_kg,
         r.actual_kg, r.vehicle, r.status, r.note)
        for r in PickupRecord.objects.filter(courier=user)
    ]
    keys = ("code", "date", "slot", "partner", "area", "est_kg", "actual_kg",
            "vehicle", "status", "note")
    result = []
    for row in rows:
        item = dict(zip(keys, row))
        y, m, d = (int(x) for x in item["date"].split("-"))
        item["date_display"] = f"{d:02d} {MONTHS_ID[m - 1]}"
        item["status_label"] = PICKUP_STATUS[item["status"]]
        actual = item["actual_kg"]
        item["actual_display"] = f"{actual:.1f}".replace(".", ",") + " kg" if actual else "–"
        result.append(item)
    return result