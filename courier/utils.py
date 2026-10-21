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
    """Data yang dikirim ke browser setelah profil diubah."""
    return {
        "display_name": get_display_name(user),
        "initials": get_initials(user),
        "email": user.email,
        "plate_number": profile.plate_number,
        "vehicle_label": profile.get_vehicle_type_display(),
        "topbar_sub": build_topbar_sub(profile),
    }


def get_courier_stats(user):
    """
    TODO: ganti dengan query ke model Pickup (status 'done', kurir = user)
    setelah model Pickup disepakati dengan modul mitra.
    """
    return {"pickups_done": 0, "total_kg": 0, "points": 0}