from django.apps import apps
from django.db.models.signals import post_save


def award_points_for_completed_pickup(sender, instance, **kwargs):
    """Credit the partner only after scheduling records a completed, weighed pickup."""
    if instance.status != 'COMPLETED' or instance.actual_weight is None:
        return

    from .services import award_verified_pickup

    reward_entry = award_verified_pickup(
        user=instance.mitra,
        kilograms=instance.actual_weight,
        pickup_reference=f'scheduling.pickupschedule:{instance.pk}',
    )
    # Keep the legacy pickup history field aligned with the authoritative reward ledger.
    if instance.points != reward_entry.points_delta:
        sender.objects.filter(pk=instance.pk).update(points=reward_entry.points_delta)
        instance.points = reward_entry.points_delta


def connect_pickup_signals():
    """Connect when the scheduling app is installed in this project checkout."""
    try:
        pickup_model = apps.get_model('scheduling', 'PickupSchedule')
    except LookupError:
        return

    post_save.connect(
        award_points_for_completed_pickup,
        sender=pickup_model,
        dispatch_uid='waste_reward.award_completed_pickup',
        weak=False,
    )
