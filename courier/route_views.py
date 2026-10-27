"""View halaman Rute Hari Ini: tampilan, mulai perjalanan, selesai pikap, dan status bertugas."""
import math
import re
from decimal import Decimal

from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.decorator import role_required

from .maps import (
    DEPOK_BOUNDS,
    STATUS_DONE,
    STATUS_ON_THE_WAY,
    build_navigation,
    describe_step,
    format_distance,
    format_duration,
    in_depok,
)
from .models import POINTS_PER_KG, CourierProfile, PickupRecord, WeightLog, points_for
from .route_plan import build_live_plan
from .route_state import (
    format_day_date,
    get_today_stops,
    reset_state,
    set_stop_state,
)
from .weather import current_weather

# Status tampilan di daftar -> teks
UI_LABELS = {
    "done": "Selesai",
    "active": "Menuju",
    "next": "Berikutnya",
    "scheduled": "Terjadwal",
}

WEIGHT_PATTERN = re.compile(r"^\d{1,4}([.,]\d)?$")  # maksimal satu angka desimal
WEIGHT_HELP = "Masukkan berat dalam kg dengan maksimal satu angka desimal, contoh 58,6."


def kg_text(value):
    """Decimal('36.4') -> '36,4'."""
    return f"{value:.1f}".replace(".", ",")


def ui_statuses(order):
    """Status tampilan tiap titik: Selesai, Menuju, Berikutnya (satu saja), sisanya Terjadwal."""
    result, next_given = {}, False
    for stop in order:
        if stop.status == STATUS_DONE:
            result[stop.pk] = "done"
        elif stop.status == STATUS_ON_THE_WAY:
            result[stop.pk] = "active"
        elif not next_given:
            result[stop.pk] = "next"
            next_given = True
        else:
            result[stop.pk] = "scheduled"
    return result


def step_icon(step):
    """Nama ikon Lucide untuk satu langkah petunjuk arah."""
    kind, modifier = step.get("type", ""), step.get("modifier", "")
    if kind == "arrive":
        return "map-pin"
    if kind in ("roundabout", "rotary", "roundabout turn", "exit roundabout", "exit rotary") or modifier == "uturn":
        return "rotate-cw"
    if "left" in modifier:
        return "arrow-left"
    if "right" in modifier:
        return "arrow-right"
    return "arrow-up"


def build_directions(route, leg_index):
    """Daftar petunjuk belok satu per satu menuju tujuan saat ini (seperti daftar langkah di Google Maps).

    Tiap langkah berisi kalimat belokan dan jarak yang ditempuh sampai belokan berikutnya.
    """
    if not route or leg_index is None or leg_index >= len(route["legs"]):
        return []

    steps = route["legs"][leg_index]["steps"]
    return [
        {
            "text": describe_step(step),
            "distance": format_distance(step["distance"]) if step["distance"] > 0 else "",
            "icon": step_icon(step),
        }
        for step in steps
    ]


# Kotak Jabodetabek: posisi kurir di luar Depok tetap dipakai sebagai titik awal petunjuk arah
NEAR_DEPOK = {"south": -6.80, "north": -5.90, "west": 106.40, "east": 107.30}


def read_origin(request):
    """Posisi kurir dari parameter lat dan lng. Hasil: ((lat, lng) atau None, catatan atau None)."""
    source = request.POST if request.method == "POST" else request.GET
    try:
        lat, lng = float(source.get("lat")), float(source.get("lng"))
    except (TypeError, ValueError):
        return None, None
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return None, None
    if in_depok(lat, lng):
        return (lat, lng), None

    b = NEAR_DEPOK
    if b["south"] <= lat <= b["north"] and b["west"] <= lng <= b["east"]:
        return (lat, lng), "Posisimu di luar Kota Depok. Petunjuk arah tetap dihitung dari posisimu, tetapi peta hanya menampilkan wilayah Depok."
    return None, "Posisimu terlalu jauh dari Kota Depok, jadi rute dihitung antar titik jemput saja."


def build_route_payload(request):
    """Satu sumber data untuk halaman penuh dan jawaban AJAX (dibaca route.js)."""
    today = timezone.localdate()
    stops = today_stops(request)
    origin, location_note = read_origin(request)

    plan = build_live_plan(stops, origin=origin, optimize=True)
    order, route = plan["order"], plan["route"]
    target_index, leg_index = plan["target_index"], plan["leg_index"]
    target = order[target_index] if target_index is not None else None
    statuses = ui_statuses(order)

    route_info = None
    if route:
        estimate = route["source"] == "estimate"
        chips = [{"text": "Perkiraan" if estimate else "OSRM", "tone": "amber" if estimate else "blue"}]
        if origin:
            chips.append({"text": "Dari posisimu", "tone": "green"})
        if plan["saving_percent"]:
            chips.append({"text": f"Hemat jarak ≈{plan['saving_percent']}%", "tone": "green"})
        route_info = {
            "label": "Rute perkiraan" if estimate else "Rute optimal",
            "summary": f"{format_distance(route['distance'])} · ±{format_duration(route['duration'])}",
            "chips": chips,
            "geometry": route["geometry"],
            "dashed": estimate,
        }

    return {
        "dateDisplay": format_day_date(today),
        "total": len(order),
        "origin": {"lat": origin[0], "lng": origin[1]} if origin else None,
        "locationNote": location_note,
        "bounds": DEPOK_BOUNDS,
        "stops": [
            {
                "id": s.pk,
                "order": i,
                "code": s.code,
                "name": s.name,
                "address": s.address,
                "slot": s.slot_text,
                "estKg": s.est_kg,
                "vehicle": s.vehicle,
                "lat": s.latitude,
                "lng": s.longitude,
                "status": statuses[s.pk],
                "statusLabel": UI_LABELS[statuses[s.pk]],
                "photoNote": s.photo_note,
                "actualKg": kg_text(s.actual_kg) if s.actual_kg is not None else None,
                "points": points_for(s.actual_kg) if s.actual_kg is not None else None,
            }
            for i, s in enumerate(order, start=1)
        ],
        "statusLabels": UI_LABELS,
        "targetId": target.pk if target else None,
        "route": route_info,
        "navigation": build_navigation(route, leg_index, target.name) if target and leg_index is not None else None,
        "directions": build_directions(route, leg_index),
        "targetName": target.name if target else None,
        "notice": plan["notice"],
        "weather": current_weather(),
        "pointsPerKg": POINTS_PER_KG,
        "dataUrl": reverse("courier:route_data"),
        "startUrl": reverse("courier:start_pickup", args=[0]).replace("/0/", "/{id}/"),
        "finishUrl": reverse("courier:finish_pickup", args=[0]).replace("/0/", "/{id}/"),
        "dutyUrl": reverse("courier:toggle_duty"),
    }


def _error(message, field="__all__", status=400):
    return JsonResponse({"ok": False, "errors": {field: [message]}}, status=status)


def today_stops(request):
    """Titik hari ini untuk kurir yang login; estimasi beratnya mengikuti armada di profilnya."""
    profile, _ = CourierProfile.objects.get_or_create(user=request.user)
    return get_today_stops(request.session, timezone.localdate(), vehicle=profile.get_vehicle_type_display())


def _find_stop(request, pk):
    stop = next((s for s in today_stops(request) if s.pk == pk), None)
    if stop is None:
        raise Http404("Titik jemput tidak ditemukan.")
    return stop


@role_required(['courier'])
def show_route_today(request):
    # ?reset=1 mengembalikan data contoh ke kondisi awal (untuk mencoba ulang)
    if request.GET.get("reset"):
        reset_state(request.session)
        return redirect("courier:show_route_today")

    profile, _ = CourierProfile.objects.get_or_create(user=request.user)
    payload = build_route_payload(request)
    return render(request, "courier/route_today.html", {
        "route": payload,
        "profile": profile,
    })


@role_required(['courier'])
@require_GET
def route_data(request):
    """Rute terbaru dari posisi kurir (AJAX, dipanggil route.js saat lokasi berubah)."""
    return JsonResponse({"ok": True, "plan": build_route_payload(request)})


def _record_pickup(request, stop, today, status, **extra):
    """Simpan atau perbarui catatan di Riwayat Pikap untuk titik ini (satu catatan per titik per hari)."""
    PickupRecord.objects.update_or_create(
        courier=request.user,
        date=today,
        code=stop.code,
        defaults=dict(
            slot=stop.slot_text,
            partner_name=stop.name,
            area=stop.address[:200],
            est_kg=stop.est_kg,
            vehicle=stop.vehicle,
            status=status,
            **extra,
        ),
    )


@role_required(['courier'])
@require_POST
def start_pickup(request, pk):
    """Mulai perjalanan ke satu titik. Hanya satu titik yang boleh berstatus menuju."""
    stop = _find_stop(request, pk)
    if stop.status == STATUS_DONE:
        return _error("Titik ini sudah selesai.")

    today = timezone.localdate()
    with transaction.atomic():
        for other in today_stops(request):
            if other.pk != stop.pk and other.status == STATUS_ON_THE_WAY:
                set_stop_state(request.session, today, other.pk, "approved")
                # Titik yang batal dituju kembali ke "Dijadwalkan"
                PickupRecord.objects.filter(
                    courier=request.user, date=today, code=other.code,
                    status=PickupRecord.Status.ONGOING,
                ).update(status=PickupRecord.Status.SCHEDULED)
        set_stop_state(request.session, today, stop.pk, STATUS_ON_THE_WAY)
        _record_pickup(request, stop, today, PickupRecord.Status.ONGOING)

    return JsonResponse({
        "ok": True,
        "message": f"Perjalanan ke {stop.name} dimulai.",
        "plan": build_route_payload(request),
    })


@role_required(['courier'])
@require_POST
def finish_pickup(request, pk):
    """Selesaikan pikap: simpan berat sebagai catatan timbangan (WeightLog)."""
    stop = _find_stop(request, pk)
    if stop.status == STATUS_DONE:
        return _error("Titik ini sudah selesai.")

    raw = (request.POST.get("weight_kg") or "").strip()
    if not WEIGHT_PATTERN.match(raw):
        return _error(WEIGHT_HELP, "weight_kg")
    weight = Decimal(raw.replace(",", "."))
    if not Decimal("0.1") <= weight <= Decimal("5000"):
        return _error("Berat harus antara 0,1 dan 5.000 kg.", "weight_kg")

    today = timezone.localdate()
    with transaction.atomic():
        WeightLog.objects.create(
            courier=request.user,
            partner_name=stop.name,
            collected_at=today,
            weight_kg=weight,
            notes=f"Pikap {stop.code}",
        )
        # Masuk juga ke Riwayat Pikap dengan status Selesai
        _record_pickup(request, stop, today, PickupRecord.Status.DONE,
                       actual_kg=weight, finished_at=timezone.now())
    set_stop_state(request.session, today, stop.pk, STATUS_DONE,
                   finished_at=timezone.now(), actual_kg=weight)

    return JsonResponse({
        "ok": True,
        "message": f"{stop.name} selesai: {kg_text(weight)} kg · +{points_for(weight)} Waste Points",
        "plan": build_route_payload(request),
    })


@role_required(['courier'])
@require_POST
def toggle_duty(request):
    """Ubah status Sedang Bertugas / Tidak Bertugas (AJAX)."""
    profile, _ = CourierProfile.objects.get_or_create(user=request.user)

    # Status dikirim eksplisit ("true"/"false"), bukan dibalik, agar aman saat klik ganda
    profile.is_on_duty = request.POST.get("on_duty") == "true"
    profile.save(update_fields=["is_on_duty"])

    return JsonResponse({
        "ok": True,
        "is_on_duty": profile.is_on_duty,
        "label": "Sedang Bertugas" if profile.is_on_duty else "Tidak Bertugas",
    })