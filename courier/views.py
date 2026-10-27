from django.contrib.auth import update_session_auth_hash
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.decorator import role_required

from .forms import (
    CourierPasswordForm,
    CourierProfileForm,
    WeightLogForm,
    errors_to_dict,
)
from .models import CourierProfile, WeightLog
from .recap import PERIODS, apply_filters, parse_filters, period_label, summarize
from .utils import (
    PICKUP_STATUS,
    format_date_id,
    get_courier_stats,
    get_display_name,
    get_initials,
    get_pickup_history,
    profile_payload,
)
from .weather import current_weather

# Jumlah baris tabel Rekap Timbangan per halaman
RECAP_PAGE_SIZE = 8


# ===================== Dashboard, rute, dan riwayat =====================
# Semua view kurir dibatasi @role_required(['courier']): hanya akun berole kurir yang bisa masuk

@role_required(['courier'])
def show_dashboard(request):
    # Diimpor di sini agar views.py tidak bergantung pada route_views saat modul dimuat
    from .dashboard import build_dashboard, build_map
    from .maps import STATUS_DONE, STATUS_ON_THE_WAY
    from .route_views import today_stops

    profile, _ = CourierProfile.objects.get_or_create(user=request.user)
    stops = today_stops(request)
    pending = [s for s in stops if s.status != STATUS_DONE]
    # Titik berikutnya: yang sedang dituju, kalau tidak ada maka yang pertama belum selesai
    next_stop = next((s for s in pending if s.status == STATUS_ON_THE_WAY), pending[0] if pending else None)

    # Angka, grafik, dan ringkasan mengikuti periode di URL (?periode=7, 30, atau 365)
    context = build_dashboard(request.user, request.GET.get("periode", ""))
    context.update({
        "profile": profile,
        "total_stops": len(stops),
        "done_stops": len(stops) - len(pending),
        "next_stop": next_stop,
        "next_stop_number": stops.index(next_stop) + 1 if next_stop else None,
        "map": build_map(stops),
        "weather": current_weather(),
    })
    return render(request, "courier/dashboard.html", context)


@role_required(['courier'])
def show_history(request):
    rows = get_pickup_history(request.user)
    counts = {key: 0 for key in PICKUP_STATUS}
    for row in rows:
        counts[row["status"]] += 1

    context = {
        "rows": rows,
        "filters": [(key, label, counts[key]) for key, label in PICKUP_STATUS.items()],
        "total": len(rows),
        "last_cancelled": next((r for r in rows if r["status"] == "cancelled"), None),
    }
    return render(request, "courier/pickup_history.html", context)


# ===================== Rekap Timbangan =====================

def build_recap_context(request):
    """Satu sumber data untuk halaman penuh dan potongan hasil (AJAX)."""
    today = timezone.localdate()

    # Membaca filter dari URL, lalu mengambil data milik kurir yang login
    filters = parse_filters(request.GET, today)
    queryset = apply_filters(WeightLog.objects.all(), request.user, filters)

    # Membagi data per halaman; get_page aman untuk nomor halaman yang salah
    paginator = Paginator(queryset, RECAP_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return {
        "filters": filters,
        "period_label": period_label(filters),
        "summary": summarize(queryset),
        "page_obj": page_obj,
        "page_range": list(
            paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1)
        ),
        "ellipsis": paginator.ELLIPSIS,
    }


@role_required(['courier'])
def show_recap(request):
    # Read (halaman penuh): filter, ringkasan, tabel, dan dialog form
    context = build_recap_context(request)
    today = timezone.localdate()
    context.update({
        "periods": PERIODS,
        "today_iso": today.isoformat(),
        "date_attrs": f'max="{today.isoformat()}"',  # Kolom tanggal tidak bisa memilih hari esok
    })
    return render(request, "courier/weight_recap.html", context)


@role_required(['courier'])
@require_GET
def recap_list(request):
    """Read (AJAX): mengembalikan HTML tabel + ringkasan sesuai filter."""
    html = render_to_string(
        "courier/components/recap_results.html",
        build_recap_context(request),
        request=request,
    )
    return JsonResponse({"html": html})


@role_required(['courier'])
@require_POST
def create_weight_log(request):
    # Create: simpan catatan baru atas nama kurir yang login
    form = WeightLogForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": errors_to_dict(form)}, status=400)

    log = form.save(commit=False)
    log.courier = request.user  # Pemilik diambil dari sesi login, bukan dari isian form
    log.save()
    return JsonResponse({"ok": True, "message": "Data timbangan ditambahkan.", "id": log.pk})


@role_required(['courier'])
@require_POST
def update_weight_log(request, pk):
    # Hanya milik kurir yang login; milik orang lain -> 404
    log = get_object_or_404(WeightLog, pk=pk, courier=request.user)

    form = WeightLogForm(request.POST, instance=log)
    if not form.is_valid():
        return JsonResponse({"ok": False, "errors": errors_to_dict(form)}, status=400)

    form.save()
    return JsonResponse({"ok": True, "message": "Data timbangan diperbarui."})


@role_required(['courier'])
@require_POST
def delete_weight_log(request, pk):
    # Delete: sama seperti update, hanya milik sendiri yang bisa dihapus
    log = get_object_or_404(WeightLog, pk=pk, courier=request.user)
    log.delete()
    return JsonResponse({"ok": True, "message": "Data timbangan dihapus."})


# ===================== Profil =====================

@role_required(['courier'])
def show_profile(request):
    # Membuat profil kurir otomatis bila belum ada
    profile, _ = CourierProfile.objects.get_or_create(user=request.user)

    context = {
        "profile": profile,
        "display_name": get_display_name(request.user),
        "initials": get_initials(request.user),
        "joined_display": format_date_id(request.user.date_joined),
        "stats": get_courier_stats(request.user),
        "vehicle_choices": CourierProfile.VehicleType.choices,
    }
    return render(request, "courier/profile.html", context)


@role_required(['courier'])
@require_POST
def update_profile(request):
    """Edit profil (AJAX). Mengembalikan JSON."""
    form = CourierProfileForm(request.POST, user=request.user)

    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": errors_to_dict(form)},
            status=400,
        )

    profile = form.save()
    return JsonResponse({
        "ok": True,
        "message": "Profil berhasil diperbarui.",
        "data": profile_payload(request.user, profile),
    })


@role_required(['courier'])
@require_POST
def change_password(request):
    """Ganti kata sandi (AJAX). Mengembalikan JSON."""
    form = CourierPasswordForm(request.user, request.POST)

    if not form.is_valid():
        return JsonResponse(
            {"ok": False, "errors": errors_to_dict(form)},
            status=400,
        )

    user = form.save()
    update_session_auth_hash(request, user)  # supaya tidak otomatis logout
    return JsonResponse({"ok": True, "message": "Kata sandi berhasil diganti."})