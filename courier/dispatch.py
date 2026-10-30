"""Penugasan pickup, pengelompokan lokasi, dan antrean redispatch kurir."""
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from scheduling.models import MitraProfile, PickupSchedule

from .maps import haversine_m, in_depok
from .models import CourierAssignment, CourierProfile


NEARBY_PICKUP_RADIUS_M = 1_000
MAX_PICKUPS_PER_ROUTE = 3
SAFE_LOAD_FACTOR = 0.8
NOMINAL_VEHICLE_CAPACITY_KG = {
    CourierProfile.VehicleType.MOTOR_BOX: 25,
    CourierProfile.VehicleType.PICKUP_BAK: 150,
}
VEHICLE_CAPACITY_KG = {
    vehicle_type: capacity * SAFE_LOAD_FACTOR
    for vehicle_type, capacity in NOMINAL_VEHICLE_CAPACITY_KG.items()
}
COURIER_VEHICLE_RANK = {
    CourierProfile.VehicleType.MOTOR_BOX: 1,
    CourierProfile.VehicleType.PICKUP_BAK: 2,
}
PICKUP_VEHICLE_RANK = {
    "Motor Box": 1,
    "Pickup Bak": 2,
}
ROUTE_PICKUP_STATUSES = ("SCHEDULED", "IN_PROGRESS", "COMPLETED")


@dataclass(frozen=True)
class DispatchResult:
    assignment: CourierAssignment | None
    reason: str | None = None


def dispatch_wait_message(reason):
    messages = {
        "missing_location": "Lengkapi titik lokasi mitra terlebih dahulu.",
        "outside_area": "Titik penjemputan harus berada di Kota Depok.",
        "unsupported_vehicle": "Belum ada kurir bertugas dengan armada yang cukup besar untuk permintaan ini.",
        "over_capacity": "Estimasi berat melebihi batas aman 80% kapasitas armada yang tersedia.",
        "no_available_courier": "Belum ada kurir disetujui dan sedang bertugas.",
        "no_capacity": "Kapasitas muatan atau batas maksimal tiga titik pada rute kurir yang tersedia sudah tercapai.",
        "no_nearby_route": "Rute kurir yang tersedia berjarak lebih dari 1 km dan tidak ada kurir kosong.",
        "not_ready": "Pengajuan belum disetujui untuk ditugaskan.",
    }
    return messages.get(reason, "Belum ada kurir yang cocok saat ini.")


def _eligible_profiles():
    return list(
        CourierProfile.objects.select_for_update()
        .filter(
            user__is_active=True,
            user__userprofile__role="courier",
            is_approved=True,
            is_on_duty=True,
        )
        .select_related("user")
        .order_by("user_id")
    )


def _candidate_load(profile, pickup):
    assignments = list(
        CourierAssignment.objects.filter(
            courier=profile.user,
            pickup_schedule__pickup_date=pickup.pickup_date,
            pickup_schedule__pickup_time_slot=pickup.pickup_time_slot,
            pickup_schedule__status__in=ROUTE_PICKUP_STATUSES,
        ).exclude(pickup_schedule_id=pickup.pk)
        .select_related("pickup_schedule__mitra")
    )
    load_kg = sum(
        float(
            row.pickup_schedule.actual_weight
            if row.pickup_schedule.status == "COMPLETED" and row.pickup_schedule.actual_weight is not None
            else row.pickup_schedule.estimated_weight
        )
        for row in assignments
    )
    capacity_kg = VEHICLE_CAPACITY_KG[profile.vehicle_type]
    if (
        len(assignments) >= MAX_PICKUPS_PER_ROUTE
        or load_kg + float(pickup.estimated_weight) > capacity_kg
    ):
        return None
    return assignments, load_kg, capacity_kg


def _choose_courier(pickup):
    profile = MitraProfile.objects.filter(user_id=pickup.mitra_id).first()
    if (
        profile is None
        or profile.latitude is None
        or profile.longitude is None
    ):
        return None, "missing_location"
    if not in_depok(profile.latitude, profile.longitude):
        return None, "outside_area"

    requested_rank = PICKUP_VEHICLE_RANK.get(pickup.armada)
    if requested_rank is None:
        return None, "unsupported_vehicle"

    maximum_supported_rank = max(COURIER_VEHICLE_RANK.values())
    if requested_rank > maximum_supported_rank:
        return None, "unsupported_vehicle"

    estimated_weight = float(pickup.estimated_weight)
    if estimated_weight > max(VEHICLE_CAPACITY_KG.values()):
        return None, "over_capacity"

    couriers = _eligible_profiles()
    if not couriers:
        return None, "no_available_courier"

    # Armada permintaan adalah kebutuhan minimum. Armada kurir yang lebih besar
    # boleh mengambilnya, tetapi armada lebih kecil tidak boleh menggantikannya.
    weight_rank = min(
        rank for vehicle_type, rank in COURIER_VEHICLE_RANK.items()
        if estimated_weight <= VEHICLE_CAPACITY_KG[vehicle_type]
    )
    required_rank = max(requested_rank, weight_rank)
    couriers = [
        courier for courier in couriers
        if COURIER_VEHICLE_RANK.get(courier.vehicle_type, 0) >= required_rank
    ]
    if not couriers:
        return None, "unsupported_vehicle"

    candidates = []
    has_capacity_but_distant_route = False
    for courier_profile in couriers:
        load = _candidate_load(courier_profile, pickup)
        if load is None:
            continue

        assignments, current_load, capacity = load
        route_distances = []
        route_locations_complete = True
        if assignments:
            partner_profiles = {
                row.user_id: row
                for row in MitraProfile.objects.filter(
                    user_id__in=[item.pickup_schedule.mitra_id for item in assignments]
                )
            }
            for assignment in assignments:
                other_profile = partner_profiles.get(assignment.pickup_schedule.mitra_id)
                if (
                    other_profile is None
                    or other_profile.latitude is None
                    or other_profile.longitude is None
                ):
                    route_locations_complete = False
                    break
                distance = haversine_m(
                    (profile.latitude, profile.longitude),
                    (other_profile.latitude, other_profile.longitude),
                )
                route_distances.append(distance)

        if assignments and (
            not route_locations_complete
            or any(distance > NEARBY_PICKUP_RADIUS_M for distance in route_distances)
        ):
            # Jangan menambahkan titik jauh ke rute yang sudah berjalan.
            has_capacity_but_distant_route = True
            continue

        vehicle_rank = COURIER_VEHICLE_RANK[courier_profile.vehicle_type]
        if assignments:
            # Prioritaskan penggabungan rute dekat, lalu kapasitas rute terendah.
            score = (0, max(route_distances), current_load / capacity,
                     len(assignments), vehicle_rank, courier_profile.user_id)
        else:
            # Kalau tidak ada rute dekat, pakai kurir kosong untuk rute mandiri.
            score = (1, current_load / capacity, len(assignments),
                     vehicle_rank, courier_profile.user_id)
        candidates.append((score, courier_profile))

    if not candidates:
        if has_capacity_but_distant_route:
            return None, "no_nearby_route"
        return None, "no_capacity"

    return min(candidates, key=lambda row: row[0])[1], None


@transaction.atomic
def dispatch_pickup(pickup_or_id):
    """Tugaskan satu pickup siap proses, atau biarkan di antrean bila belum ada kurir cocok."""
    pickup_id = getattr(pickup_or_id, "pk", pickup_or_id)
    pickup = PickupSchedule.objects.select_for_update().get(pk=pickup_id)

    existing = (
        CourierAssignment.objects.select_related("courier")
        .filter(pickup_schedule=pickup)
        .first()
    )
    if existing:
        if pickup.status == "APPROVED":
            pickup.status = "SCHEDULED"
            pickup.save(update_fields=["status"])
        return DispatchResult(existing)

    if pickup.status not in ("APPROVED", "SCHEDULED"):
        return DispatchResult(None, "not_ready")

    courier_profile, reason = _choose_courier(pickup)
    if courier_profile is None:
        if pickup.status != "APPROVED":
            pickup.status = "APPROVED"
            pickup.save(update_fields=["status"])
        return DispatchResult(None, reason)

    assignment, _ = CourierAssignment.objects.get_or_create(
        pickup_schedule=pickup,
        defaults={"courier": courier_profile.user},
    )
    if pickup.status != "SCHEDULED":
        pickup.status = "SCHEDULED"
        pickup.save(update_fields=["status"])
    return DispatchResult(assignment)


def dispatch_pending_pickups(limit=50):
    """Coba ulang pickup yang admin setujui tetapi belum mendapat kurir."""
    pickup_ids = list(
        PickupSchedule.objects.filter(
            status="APPROVED",
            courier_assignment__isnull=True,
            pickup_date__gte=timezone.localdate(),
        )
        .order_by("pickup_date", "pickup_time_slot", "created_at", "pk")
        .values_list("pk", flat=True)[:limit]
    )
    return [dispatch_pickup(pickup_id) for pickup_id in pickup_ids]
