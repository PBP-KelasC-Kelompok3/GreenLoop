"""Logika filter periode dan ringkasan untuk halaman Rekap Timbangan."""
from datetime import date, timedelta
from decimal import Decimal

from .models import points_for
from .utils import format_date_id

# Pilihan periode di tombol filter: (nilai di URL, tulisan di tombol)
PERIODS = [
    ("today", "Hari ini"),
    ("week", "7 hari"),
    ("month", "Bulan ini"),
    ("all", "Semua"),
]
VALID_PERIODS = {value for value, _ in PERIODS} | {"custom"}
DEFAULT_PERIOD = "month"


def _parse_date(text):
    # Mengubah teks 'YYYY-MM-DD' menjadi tanggal; teks rusak menjadi None (tidak error)
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError:
        return None


def parse_filters(params, today):
    """Membaca ?period=&start=&end=&q= dengan aman. Nilai aneh diabaikan."""
    # Periode yang tidak dikenal kembali ke 'bulan ini'
    period = params.get("period", DEFAULT_PERIOD)
    if period not in VALID_PERIODS:
        period = DEFAULT_PERIOD

    start = _parse_date(params.get("start"))
    end = _parse_date(params.get("end"))

    # Rentang kustom: tanpa tanggal sama sekali dianggap 'bulan ini', tanggal terbalik ditukar
    if period == "custom":
        if not (start or end):
            period = DEFAULT_PERIOD
        elif start and end and start > end:
            start, end = end, start

    # Menentukan batas tanggal untuk tiap periode
    if period == "today":
        date_from, date_to = today, today
    elif period == "week":
        date_from, date_to = today - timedelta(days=6), today
    elif period == "month":
        date_from, date_to = today.replace(day=1), today
    elif period == "custom":
        date_from, date_to = start, end
    else:  # all
        date_from, date_to = None, None

    return {
        "period": period,
        "q": (params.get("q") or "").strip()[:60],
        "date_from": date_from,
        "date_to": date_to,
        # nilai yang ditampilkan kembali di kolom tanggal (hanya untuk rentang kustom)
        "start_value": date_from.isoformat() if period == "custom" and date_from else "",
        "end_value": date_to.isoformat() if period == "custom" and date_to else "",
    }


def apply_filters(queryset, user, filters):
    """Kurir hanya boleh melihat catatan miliknya sendiri."""
    queryset = queryset.filter(courier=user)

    # Menyaring berdasarkan tanggal dan kata kunci nama mitra
    if filters["date_from"]:
        queryset = queryset.filter(collected_at__gte=filters["date_from"])
    if filters["date_to"]:
        queryset = queryset.filter(collected_at__lte=filters["date_to"])
    if filters["q"]:
        queryset = queryset.filter(partner_name__icontains=filters["q"])
    return queryset


def summarize(queryset):
    # Menghitung total berat, total poin, jumlah catatan, dan rata-rata dari data yang sudah difilter
    weights = list(queryset.values_list("weight_kg", flat=True))
    count = len(weights)
    total = sum(weights, Decimal("0"))

    return {
        "count": count,
        "total": total,
        "points": sum(points_for(w) for w in weights),
        "average": (total / count) if count else Decimal("0"),
    }


def period_label(filters):
    # Membuat tulisan periode untuk judul tabel, contoh: "1 Okt 2026 – 21 Okt 2026"
    date_from, date_to = filters["date_from"], filters["date_to"]

    if not date_from and not date_to:
        return "Semua periode"
    if date_from and not date_to:
        return f"Mulai {format_date_id(date_from)}"
    if date_to and not date_from:
        return f"Sampai {format_date_id(date_to)}"
    if date_from == date_to:
        return format_date_id(date_from)
    return f"{format_date_id(date_from)} – {format_date_id(date_to)}"