"""Menyusun rute dari posisi kurir sekarang menuju titik jemput yang belum selesai.

Memakai fungsi dasar dari maps.py (OSRM + cadangan), tetapi titik awalnya posisi
kurir (bila lokasi aktif), bukan gudang. Titik yang sudah selesai tidak ikut digambar.
Bila lokasi belum aktif, rute hanya menghubungkan titik-titik jemput itu sendiri.
"""
from .maps import (
    STATUS_APPROVED,
    STATUS_DONE,
    STATUS_ON_THE_WAY,
    RoutingError,
    fetch_trip_order,
    get_route,
    nearest_neighbor_order,
)


def _point(stop):
    return (float(stop.latitude), float(stop.longitude))


def build_live_plan(stops, origin=None, optimize=True):
    """Hasil: urutan titik, rute, penghematan, tujuan saat ini, dan indeks leg tujuan itu.

    origin: (lat, lng) posisi kurir, atau None bila lokasi belum aktif.
    """
    by_slot = sorted(stops, key=lambda s: (s.slot_start, s.pk))
    done = sorted(
        (s for s in by_slot if s.status == STATUS_DONE),
        key=lambda s: (s.finished_at is None, s.finished_at.timestamp() if s.finished_at else 0, s.pk),
    )
    active = [s for s in by_slot if s.status == STATUS_ON_THE_WAY]
    free = [s for s in by_slot if s.status == STATUS_APPROVED]
    notice = None

    def optimized(candidates, anchor):
        # Mengurutkan titik bebas dengan layanan trip OSRM; cadangannya titik terdekat berikutnya
        nonlocal notice
        offset = 1 if anchor is not None else 0
        points = ([anchor] if anchor is not None else []) + [_point(s) for s in candidates]
        if len(points) < 3:
            return candidates
        try:
            indexes = fetch_trip_order(points)
        except RoutingError:
            indexes = nearest_neighbor_order(points)
            notice = "Layanan peta tidak merespons, urutan dihitung dari jarak garis lurus."
        return [candidates[i - offset] for i in indexes if i >= offset]

    anchor = _point(active[-1]) if active else origin
    new_free = optimized(free, anchor) if optimize and len(free) >= 2 else free

    order = done + active + new_free
    pending = active + new_free

    def path(pending_stops):
        points = [_point(s) for s in pending_stops]
        return ([origin] + points) if origin else points

    route = get_route(path(pending)) if len(path(pending)) >= 2 else None
    if route and route["source"] == "estimate" and notice is None:
        notice = "Layanan peta sedang tidak tersedia, rute berupa perkiraan garis lurus."

    # Penghematan dibanding urutan jadwal (hanya bila sumber hitungnya sama)
    saving_percent = None
    if route and optimize and new_free != free:
        baseline = get_route(path(active + free))
        if baseline["source"] == route["source"] and baseline["distance"] > 0:
            saving_percent = max(0, round((baseline["distance"] - route["distance"]) / baseline["distance"] * 100))

    # Tujuan saat ini: yang sedang dituju, kalau tidak ada maka yang berikutnya
    target = (active or new_free or [None])[0]
    target_index = order.index(target) if target else None

    leg_index = None
    if route and target:
        k = pending.index(target)
        leg_index = k if origin else k - 1      # tanpa lokasi, titik pertama adalah awal rute
        if not 0 <= leg_index < len(route["legs"]):
            leg_index = None

    return {
        "order": order,
        "route": route,
        "saving_percent": saving_percent,
        "target_index": target_index,
        "leg_index": leg_index,
        "notice": notice,
    }