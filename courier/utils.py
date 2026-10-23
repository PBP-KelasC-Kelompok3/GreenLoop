MONTHS_ID = [
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]


def get_display_name(user):
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
    rows = [
        ("PK-0941", "2026-10-06", "08.00–10.00", "Kafe Senja Margonda", "Beji", 30, None, "Pickup Bak", "scheduled", ""),
        ("PK-0940", "2026-10-03", "08.00–10.00", "Resto Sari Rasa", "Pancoran Mas", 35, None, "Pickup Bak", "ongoing", ""),
        ("PK-0938", "2026-09-29", "13.00–15.00", "Warung Bu Tini", "Cimanggis", 20, None, "Motor Box", "ongoing", ""),
        ("PK-0931", "2026-09-26", "08.00–10.00", "Kafe Senja Margonda", "Beji", 35, 35.2, "Pickup Bak", "done", ""),
        ("PK-0924", "2026-09-19", "08.00–10.00", "Katering Nusantara", "Sukmajaya", 40, 41.0, "Pickup Bak", "done", ""),
        ("PK-0917", "2026-09-12", "13.00–15.00", "Resto Sari Rasa", "Pancoran Mas", 30, None, "Pickup Bak", "cancelled",
         "Foto limbah tercampur plastik dan styrofoam, penjemputan dibatalkan oleh admin."),
        ("PK-0910", "2026-09-05", "08.00–10.00", "Warung Bu Tini", "Cimanggis", 25, 22.8, "Motor Box", "done", ""),
        ("PK-0903", "2026-08-29", "08.00–10.00", "Katering Nusantara", "Sukmajaya", 30, 31.4, "Pickup Bak", "done", ""),
        ("PK-0897", "2026-08-22", "13.00–15.00", "Kafe Senja Margonda", "Beji", 28, 27.5, "Pickup Bak", "done", ""),
        ("PK-0889", "2026-08-15", "08.00–10.00", "Resto Sari Rasa", "Pancoran Mas", 32, 33.1, "Pickup Bak", "done", ""),
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