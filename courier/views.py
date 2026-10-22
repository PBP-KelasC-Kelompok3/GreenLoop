from django.contrib.auth import update_session_auth_hash
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from accounts.decorator import role_required

from .forms import CourierPasswordForm, CourierProfileForm, errors_to_dict
from .models import CourierProfile
from .utils import (
    PICKUP_STATUS,
    format_date_id,
    get_courier_stats,
    get_display_name,
    get_initials,
    get_pickup_history,
    profile_payload,
)


@role_required(['courier'])
def show_dashboard(request):
    return render(request, "courier/dashboard.html")


@role_required(['courier'])
def show_route_today(request):
    return render(request, "courier/route_today.html")


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


@role_required(['courier'])
def show_recap(request):
    return render(request, "courier/weight_recap.html")


@role_required(['courier'])
def show_profile(request):
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