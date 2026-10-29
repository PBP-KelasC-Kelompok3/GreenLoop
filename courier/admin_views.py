from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.permissions import can_manage_greenloop

from .dispatch import dispatch_pending_pickups, dispatch_pickup, dispatch_wait_message
from .models import CourierProfile


@login_required
def admin_verify_couriers(request):
    if not can_manage_greenloop(request.user):
        return redirect("home")

    context = {
        "pending_couriers": CourierProfile.objects.filter(
            is_approved=False,
        ).select_related("user"),
        "approved_couriers": CourierProfile.objects.filter(
            is_approved=True,
        ).select_related("user"),
    }
    return render(request, "courier/admin_verify_couriers.html", context)


@login_required
def approve_courier(request, courier_id):
    if not can_manage_greenloop(request.user):
        return redirect("home")

    profile = get_object_or_404(CourierProfile, pk=courier_id)
    profile.is_approved = True
    profile.save(update_fields=["is_approved"])
    if profile.is_on_duty:
        dispatch_pending_pickups()
    messages.success(request, f"Akun kurir {profile.user.username} disetujui.")
    return redirect("courier:admin_verify_couriers")


@login_required
def redispatch_pickup(request, pickup_id):
    if not can_manage_greenloop(request.user):
        return redirect("home")

    result = dispatch_pickup(pickup_id)
    if result.assignment:
        name = result.assignment.courier.get_full_name() or result.assignment.courier.username
        messages.success(request, f"Pickup ditugaskan kepada {name}.")
    else:
        messages.warning(request, dispatch_wait_message(result.reason))
    return redirect("admin_dashboard")
