"""Layanan peta untuk halaman Rute Hari Ini.

Memakai API publik tanpa API key:
- OSRM (data OpenStreetMap): rute jalan, jarak, durasi, petunjuk belok, dan urutan kunjungan.
Bila layanan tidak merespons, rute dihitung kasar (garis lurus) agar halaman tetap berfungsi.
"""
import json
import math
import os
import urllib.error
import urllib.request

from django.core.cache import cache

DEFAULT_OSRM_URL = "https://router.project-osrm.org"
REQUEST_TIMEOUT = 8  # detik
CACHE_SECONDS = 300  # jawaban yang sama disimpan 5 menit agar API tidak dipanggil berulang
USER_AGENT = "GreenLoop-Courier/1.0 (tugas kuliah)"

# Perkiraan batas wilayah Kota Depok (dipakai membatasi peta dan memvalidasi titik jemput)
DEPOK_BOUNDS = {"south": -6.46, "north": -6.32, "west": 106.72, "east": 106.92}

# Titik awal kurir setiap hari
DEPOT = {"name": "Gudang GreenLoop Depok", "lat": -6.3715, "lng": 106.8310}

# Nilai status yang sama dengan Pickup.Status (ditulis ulang agar modul ini tidak bergantung pada model)
STATUS_DONE = "done"
STATUS_ON_THE_WAY = "on_the_way"
STATUS_APPROVED = "approved"

# Dipakai saat OSRM tidak bisa dihubungi: jalan dianggap 1,35x lebih panjang dari garis lurus, kecepatan 22 km/jam
ROAD_FACTOR = 1.35
AVERAGE_SPEED_MS = 22 * 1000 / 3600


class RoutingError(Exception):
    """Layanan peta tidak bisa dipakai (jaringan mati, jawaban tidak valid, dsb.)."""


def osrm_base_url():
    # Alamat bisa diganti lewat variabel lingkungan OSRM_BASE_URL (mis. server OSRM sendiri)
    return os.environ.get("OSRM_BASE_URL", DEFAULT_OSRM_URL).rstrip("/")


def in_depok(lat, lng):
    """True bila koordinat berada di dalam kotak perkiraan wilayah Kota Depok."""
    b = DEPOK_BOUNDS
    return b["south"] <= lat <= b["north"] and b["west"] <= lng <= b["east"]


def haversine_m(a, b):
    """Jarak garis lurus (meter) antara dua titik (lat, lng)."""
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


# --------------- format tampilan ---------------

def format_distance(meters):
    """350 -> '350 m'; 12600 -> '12,6 km'."""
    if meters < 1000:
        return f"{int(round(meters / 10.0) * 10) if meters >= 100 else int(round(meters))} m"
    return f"{meters / 1000:.1f} km".replace(".", ",")


def format_duration(seconds):
    """2880 -> '48 menit'; 5400 -> '1 jam 30 menit'."""
    minutes = max(1, int(round(seconds / 60)))
    if minutes >= 60:
        hours, rest = divmod(minutes, 60)
        return f"{hours} jam {rest} menit" if rest else f"{hours} jam"
    return f"{minutes} menit"


# Arah belok dalam bahasa Indonesia
TURN_WORDS = {
    "left": "kiri",
    "right": "kanan",
    "slight left": "serong kiri",
    "slight right": "serong kanan",
    "sharp left": "tajam ke kiri",
    "sharp right": "tajam ke kanan",
}


def describe_step(step):
    """Mengubah satu langkah OSRM menjadi kalimat, contoh: 'Belok kiri ke Jl. Margonda Raya'."""
    kind = step.get("type", "")
    modifier = step.get("modifier", "")
    name = (step.get("name") or "").strip()
    road = f" ke {name}" if name else ""

    if kind == "arrive":
        return "Tiba di tujuan"
    if kind == "depart":
        return f"Mulai perjalanan di {name}" if name else "Mulai perjalanan"
    if kind in ("exit roundabout", "exit rotary"):
        return f"Keluar dari bundaran{road}"
    if kind in ("roundabout", "rotary", "roundabout turn"):
        return f"Masuk bundaran{road}"
    if modifier == "uturn":
        return f"Putar balik{road}"
    if modifier in TURN_WORDS:
        return f"Belok {TURN_WORDS[modifier]}{road}"
    if kind in ("fork", "merge", "on ramp", "off ramp"):
        return f"Ambil jalur{road}"
    return f"Lurus{road}"


# --------------- panggilan API ---------------

def _fetch_json(url):
    """GET JSON dari layanan luar, dengan batas waktu dan penyimpanan sementara (cache)."""
    cached = cache.get(url)
    if cached is not None:
        return cached

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RoutingError(f"Layanan peta tidak merespons: {exc}") from exc

    cache.set(url, data, CACHE_SECONDS)
    return data


def _coords(points):
    # OSRM memakai urutan longitude,latitude dipisah titik koma
    return ";".join(f"{lng:.6f},{lat:.6f}" for lat, lng in points)


def fetch_route(points):
    """Rute jalan melewati titik-titik sesuai urutan (OSRM route service)."""
    if len(points) < 2:
        raise RoutingError("Rute butuh minimal dua titik.")

    url = f"{osrm_base_url()}/route/v1/driving/{_coords(points)}?overview=full&geometries=geojson&steps=true"
    data = _fetch_json(url)
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(data.get("message") or data.get("code") or "Jawaban OSRM tidak valid.")

    route = data["routes"][0]
    try:
        return {
            "source": "osrm",
            # GeoJSON berurutan [lng, lat]; Leaflet butuh [lat, lng]
            "geometry": [[lat, lng] for lng, lat in route["geometry"]["coordinates"]],
            "distance": route["distance"],
            "duration": route["duration"],
            "legs": [
                {
                    "distance": leg["distance"],
                    "duration": leg["duration"],
                    "steps": [
                        {
                            "distance": step["distance"],
                            "name": step.get("name", ""),
                            "type": step["maneuver"]["type"],
                            "modifier": step["maneuver"].get("modifier", ""),
                        }
                        for step in leg.get("steps", [])
                    ],
                }
                for leg in route["legs"]
            ],
        }
    except (KeyError, TypeError) as exc:
        raise RoutingError("Format jawaban OSRM tidak dikenali.") from exc


def fetch_trip_order(points):
    """Urutan kunjungan terbaik (OSRM trip service). Titik pertama tetap menjadi titik awal.

    Mengembalikan daftar indeks titik input sesuai urutan kunjungan, contoh: [0, 2, 1, 3].
    Catatan: OSRM hanya mendukung 'tanpa roundtrip' bila source=first DAN destination=last,
    jadi di sini dipakai roundtrip=true lalu bagian kembali ke titik awal diabaikan.
    """
    if len(points) < 3:
        return list(range(len(points)))

    url = f"{osrm_base_url()}/trip/v1/driving/{_coords(points)}?roundtrip=true&source=first&overview=false&steps=false"
    data = _fetch_json(url)
    if data.get("code") != "Ok":
        raise RoutingError(data.get("message") or data.get("code") or "Jawaban OSRM tidak valid.")

    try:
        positions = [waypoint["waypoint_index"] for waypoint in data["waypoints"]]
    except (KeyError, TypeError) as exc:
        raise RoutingError("Format jawaban OSRM tidak dikenali.") from exc

    if sorted(positions) != list(range(len(points))):
        raise RoutingError("Urutan kunjungan dari OSRM tidak lengkap.")

    order = sorted(range(len(points)), key=lambda i: positions[i])
    if order[0] != 0:
        raise RoutingError("Urutan kunjungan tidak dimulai dari titik awal.")
    return order


# --------------- cadangan bila API mati ---------------

def estimate_route(points):
    """Rute perkiraan (garis lurus x faktor jalan), dipakai bila OSRM tidak bisa dihubungi."""
    legs = []
    total = 0.0
    geometry = [list(points[0])]

    for start, end in zip(points, points[1:]):
        distance = haversine_m(start, end) * ROAD_FACTOR
        legs.append({"distance": distance, "duration": distance / AVERAGE_SPEED_MS, "steps": []})
        geometry.append(list(end))
        total += distance

    return {
        "source": "estimate",
        "geometry": geometry,
        "distance": total,
        "duration": total / AVERAGE_SPEED_MS,
        "legs": legs,
    }


def nearest_neighbor_order(points):
    """Urutan 'selalu ke titik terdekat berikutnya', mulai dari titik pertama."""
    remaining = list(range(1, len(points)))
    order = [0]
    while remaining:
        last = points[order[-1]]
        nearest = min(remaining, key=lambda i: haversine_m(last, points[i]))
        remaining.remove(nearest)
        order.append(nearest)
    return order


def get_route(points):
    # Memakai OSRM; bila gagal, jatuh ke rute perkiraan
    try:
        return fetch_route(points)
    except RoutingError:
        return estimate_route(points)


# --------------- perencanaan rute harian ---------------

def _point(pickup):
    return (float(pickup.latitude), float(pickup.longitude))


def build_plan(pickups, optimize=False):
    """Menyusun urutan penjemputan dan rutenya.

    Urutan: pikap yang sudah selesai, lalu yang sedang berjalan, lalu sisanya
    (berdasarkan jam slot, atau berdasarkan jarak terpendek bila optimize=True).
    """
    by_slot = sorted(pickups, key=lambda p: (p.slot_start, p.pk))
    done = sorted(
        (p for p in by_slot if p.status == STATUS_DONE),
        key=lambda p: (p.finished_at is None, p.finished_at.timestamp() if p.finished_at else 0, p.pk),
    )
    active = [p for p in by_slot if p.status == STATUS_ON_THE_WAY]
    free = [p for p in by_slot if p.status == STATUS_APPROVED]

    prefix = done + active
    depot = (DEPOT["lat"], DEPOT["lng"])
    schedule_order = prefix + free
    order = schedule_order
    notice = None

    # Optimalkan hanya titik yang belum dikerjakan; titik awalnya adalah posisi terakhir kurir
    if optimize and len(free) >= 2:
        anchor = _point(prefix[-1]) if prefix else depot
        points = [anchor] + [_point(p) for p in free]
        try:
            indexes = fetch_trip_order(points)
        except RoutingError:
            indexes = nearest_neighbor_order(points)
            notice = "Layanan peta tidak merespons, urutan dihitung dari jarak garis lurus."
        order = prefix + [free[i - 1] for i in indexes[1:]]

    def path(stops):
        return [depot] + [_point(p) for p in stops]

    route = get_route(path(order)) if order else None
    if route and route["source"] == "estimate" and notice is None:
        notice = "Layanan peta sedang tidak tersedia, rute berupa perkiraan garis lurus."

    # Penghematan jarak dibanding urutan jadwal (hanya dibandingkan bila sumber hitungnya sama)
    saving_percent = None
    if route and optimize and order != schedule_order:
        baseline = get_route(path(schedule_order))
        if baseline["source"] == route["source"] and baseline["distance"] > 0:
            saving_percent = max(0, round((baseline["distance"] - route["distance"]) / baseline["distance"] * 100))

    # Tujuan saat ini: pikap yang sedang berjalan, kalau tidak ada maka yang berikutnya
    target_index = next((i for i, p in enumerate(order) if p.status == STATUS_ON_THE_WAY), None)
    if target_index is None:
        target_index = next((i for i, p in enumerate(order) if p.status == STATUS_APPROVED), None)

    return {
        "order": order,
        "route": route,
        "optimized": bool(optimize and order != schedule_order),
        "saving_percent": saving_percent,
        "target_index": target_index,
        "notice": notice,
    }


def build_navigation(route, target_index, target_name):
    """Petunjuk belok berikutnya menuju tujuan saat ini (kartu hijau di bawah peta)."""
    if not route or target_index is None or target_index >= len(route["legs"]):
        return None

    leg = route["legs"][target_index]
    steps = leg["steps"]
    if len(steps) >= 2:
        # Jarak sampai belokan berikutnya, lalu kalimat belokannya
        return {
            "distance_text": format_distance(steps[0]["distance"]),
            "instruction": describe_step(steps[1]),
            "target": target_name,
        }
    return {
        "distance_text": format_distance(leg["distance"]),
        "instruction": f"Menuju {target_name}",
        "target": target_name,
    }