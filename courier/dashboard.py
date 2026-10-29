"""Data untuk Dashboard Kurir: statistik per periode, grafik, sumber limbah, dan peta mini hari ini.

Semua angka dihitung dari catatan pikap milik kurir yang login (PickupRecord berstatus selesai),
jadi dashboard ikut berubah setiap kali kurir menyelesaikan satu titik.
"""
import math
from datetime import date, datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from .models import PickupRecord, points_for
from .utils import MONTHS_ID
from scheduling.models import MitraProfile

WIB = dt_timezone(timedelta(hours=7))

MONTHS_FULL = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

# Kunci di URL (?periode=...) -> label tombol
RANGES = {"7": "7 Hari", "30": "30 Hari", "365": "12 Bulan"}
DEFAULT_RANGE = "365"

# ---------- Format angka (titik ribuan, koma desimal) ----------

def fmt_number(value, decimals=None):
    """12480 -> '12.480'; 7.5 -> '7,5'. decimals=None: satu desimal hanya bila perlu."""
    value = Decimal(str(value))
    if decimals is None:
        decimals = 0 if value == value.to_integral_value() else 1
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def fmt_kg(value):
    return f"{fmt_number(value)} kg"


def delta_badge(current, previous):
    """Persentase perubahan dibanding periode sebelumnya: dict(text, tone) atau None."""
    current, previous = Decimal(str(current)), Decimal(str(previous))
    if previous > 0:
        pct = (current - previous) / previous * 100
        sign = "+" if pct >= 0 else "−"
        return {"text": f"{sign}{fmt_number(abs(pct), 1)}%", "tone": "up" if pct >= 0 else "down"}
    return None   # periode sebelumnya kosong: belum ada pembanding yang berarti


def _nice_step(raw):
    """Pembulatan ke atas ke 1, 2, 2,5, 5 atau 10 kali pangkat sepuluh."""
    if raw <= 0:
        return 1
    exp = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * exp:
            return m * exp
    return 10 * exp


# ---------- Periode ----------

def period_bounds(range_key, today):
    """Mengembalikan (mulai, akhir, mulai_sebelumnya, akhir_sebelumnya, per_bulan)."""
    if range_key == "365":
        start = _add_months(today.replace(day=1), -11)
        prev_start = _add_months(start, -12)
        return start, today, prev_start, start - timedelta(days=1), True
    days = int(range_key)
    start = today - timedelta(days=days - 1)
    return start, today, start - timedelta(days=days), start - timedelta(days=1), False


def _add_months(first_of_month, delta):
    index = first_of_month.year * 12 + first_of_month.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1)


def build_chart(records, start, end, monthly):
    """Batang kg per hari atau per bulan, lengkap dengan garis bantu sumbu Y."""
    buckets = []   # (kunci, label pendek, label panjang)
    if monthly:
        cursor = start
        while cursor <= end:
            buckets.append(((cursor.year, cursor.month), MONTHS_ID[cursor.month - 1],
                            f"{MONTHS_FULL[cursor.month - 1]} {cursor.year}"))
            cursor = _add_months(cursor, 1)
    else:
        for i in range((end - start).days + 1):
            day = start + timedelta(days=i)
            buckets.append((day, f"{day.day} {MONTHS_ID[day.month - 1]}",
                            f"{day.day} {MONTHS_ID[day.month - 1]} {day.year}"))

    totals = {key: Decimal("0") for key, _, _ in buckets}
    for rec in records:
        key = (rec.date.year, rec.date.month) if monthly else rec.date
        if key in totals:
            totals[key] += rec.actual_kg

    # Sumbu Y dibulatkan supaya garis bantunya mudah dibaca (empat sekat)
    peak = max(totals.values())
    step = _nice_step(float(peak) / 4) if peak > 0 else 2.5
    top = step * 4
    ticks = [{"value": fmt_number(step * i), "bottom": round(25 * i, 2)} for i in range(5)]

    bars = []
    # Label sumbu X dijarangkan untuk 30 hari agar tidak bertumpuk; label terakhir selalu tampil
    every = 1 if (monthly or len(buckets) <= 7) else 5
    for i, (key, short, long_) in enumerate(buckets):
        kg = totals[key]
        height = round(float(kg) / top * 100, 2) if kg > 0 else 0
        bars.append({
            "label": short if i % every == (len(buckets) - 1) % every else "",
            "tip_title": long_,
            "tip_value": fmt_kg(kg),
            "height": max(height, 2) if kg > 0 else 0,
            "is_last": i == len(buckets) - 1,
        })

    first_long, last_long = buckets[0][2], buckets[-1][2]
    subtitle = f"dalam kilogram · {first_long} – {last_long}"
    return {"bars": bars, "ticks": ticks, "subtitle": subtitle}


def build_composition(records):
    """Persentase kg menurut jenis mitra sumber limbah (kafe, restoran, hotel, dst.).

    Limbah yang diterima GreenLoop selalu kulit buah dan sayur kering yang belum tercampur,
    jadi yang dibandingkan adalah dari mana limbah itu berasal, bukan jenis limbahnya.
    """
    category = {}
    for record in records:
        schedule = record.pickup_schedule
        mitra_profile = MitraProfile.objects.filter(
            user_id=schedule.mitra_id,
        ).only("business_type").first() if schedule else None
        if mitra_profile and mitra_profile.business_type:
            category[record.code] = mitra_profile.business_type
    by_source = {}
    for rec in records:
        source = category.get(rec.code) or "Lainnya"
        by_source[source] = by_source.get(source, Decimal("0")) + rec.actual_kg
    total = sum(by_source.values(), Decimal("0"))
    if total <= 0:
        return []
    ordered = sorted(by_source.items(), key=lambda item: (item[0] == "Lainnya", -item[1]))
    if len(ordered) > 4:
        rest = sum((kg for _, kg in ordered[3:]), Decimal("0"))
        ordered = ordered[:3] + [("Lainnya", rest)]
    return [{"label": name, "percent": pct} for (name, _), pct in zip(ordered, _percentages([kg for _, kg in ordered]))]


def _percentages(values):
    """Persentase bulat yang selalu berjumlah 100 (metode sisa terbesar)."""
    total = sum(values)
    raw = [v / total * 100 for v in values]
    floors = [int(r) for r in raw]
    # Sisa poin dibagikan ke angka dengan pecahan terbesar
    order = sorted(range(len(values)), key=lambda i: raw[i] - floors[i], reverse=True)
    for i in order[:100 - sum(floors)]:
        floors[i] += 1
    return floors


def build_map(stops):
    """Posisi pin 0-100% untuk peta mini bergaya skema (bukan peta jalan sungguhan)."""
    if not stops:
        return {"pins": [], "path": ""}
    # Koreksi lebar derajat bujur menurut garis lintang supaya jarak tidak melar ke samping
    mid_lat = sum(s.latitude for s in stops) / len(stops)
    k = math.cos(math.radians(mid_lat))
    xs = [s.longitude * k for s in stops]
    ys = [-s.latitude for s in stops]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    # Kotak peta kira-kira 2 : 1; sisakan ruang untuk label di atas dan kartu di bawah (pin tidak tertutup)
    left, top, box_w, box_h = 8, 24, 84, 36
    span_x, span_y = max(max_x - min_x, 1e-9), max(max_y - min_y, 1e-9)
    scale = min(box_w * 2 / span_x, box_h / span_y)       # sumbu x dihitung lebih panjang (2:1)
    used_w, used_h = span_x * scale / 2, span_y * scale
    off_x, off_y = left + (box_w - used_w) / 2, top + (box_h - used_h) / 2

    # Pin diberi nomor sesuai urutan jadwal; status dipakai untuk warna pin
    pins = []
    for i, s in enumerate(stops):
        pins.append({
            "num": i + 1,
            "name": s.name,
            "x": round(off_x + (xs[i] - min_x) * scale / 2, 2),
            "y": round(off_y + (ys[i] - min_y) * scale, 2),
            "status": s.status,
        })
    path = " ".join(f"{p['x']},{p['y']}" for p in pins)
    return {"pins": pins, "path": path}


def build_dashboard(user, range_key, today=None, now=None):
    """Seluruh data halaman (tanpa bagian rute hari ini, yang diambil dari sesi di view)."""
    if range_key not in RANGES:
        range_key = DEFAULT_RANGE
    now = now or datetime.now(WIB)
    today = today or now.date()
    start, end, prev_start, prev_end, monthly = period_bounds(range_key, today)

    # Satu kali query untuk periode ini dan periode sebelumnya, lalu dipisah di Python
    done = list(PickupRecord.objects.filter(
        courier=user, status=PickupRecord.Status.DONE, actual_kg__isnull=False,
        date__gte=prev_start, date__lte=end,
    ))
    current = [r for r in done if start <= r.date <= end]
    previous = [r for r in done if prev_start <= r.date <= prev_end]

    def totals(rows):
        kg = sum((r.actual_kg for r in rows), Decimal("0"))
        return {
            "kg": kg,
            "pickups": len(rows),
            "points": sum(points_for(r.actual_kg) for r in rows),
            "partners": len({r.partner_name for r in rows}),
        }

    cur, prev = totals(current), totals(previous)
    # Empat kartu angka; delta membandingkan periode ini dengan periode sebelumnya
    kpis = [
        {"key": "kg", "icon": "leaf", "label": "Total limbah terkumpul", "value": fmt_kg(cur["kg"]),
         "delta": delta_badge(cur["kg"], prev["kg"]), "dark": True},
        {"key": "pickups", "icon": "package", "label": "Pikap selesai", "value": fmt_number(cur["pickups"]),
         "delta": delta_badge(cur["pickups"], prev["pickups"])},
        {"key": "points", "icon": "star", "label": "Waste Points", "value": fmt_number(cur["points"]),
         "delta": delta_badge(cur["points"], prev["points"])},
        {"key": "partners", "icon": "pin", "label": "Mitra dilayani", "value": fmt_number(cur["partners"]),
         "delta": delta_badge(cur["partners"], prev["partners"])},
    ]

    # Ringkasan performa di banner bawah
    heaviest = max(current, key=lambda r: r.actual_kg, default=None)
    summary = [
        {"icon": "leaf", "value": fmt_kg(cur["kg"] / cur["pickups"]) if cur["pickups"] else "–",
         "caption": "rata-rata berat per pikap"},
        {"icon": "truck", "value": fmt_kg(heaviest.actual_kg) if heaviest else "–",
         "caption": f"pikap terberat · {heaviest.partner_name}" if heaviest else "pikap terberat"},
        {"icon": "calendar", "value": f"{len({r.date for r in current})} hari",
         "caption": "pikap selesai pada periode ini"},
    ]

    return {
        "range_key": range_key,
        "ranges": [(key, label) for key, label in RANGES.items()],
        "kpis": kpis,
        "chart": build_chart(current, start, end, monthly),
        "chart_title": "Limbah terkumpul per " + ("bulan" if monthly else "hari"),
        "composition": build_composition(current),
        "summary": summary,
        "updated_display": f"{now.day} {MONTHS_ID[now.month - 1]} {now.year}, {now:%H.%M} WIB",
    }
