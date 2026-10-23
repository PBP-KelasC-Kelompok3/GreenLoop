from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import RewardTransaction, RewardVoucher, UserVoucher


POINTS_PER_KILOGRAM = 5


class InsufficientPoints(Exception):
    """Raised when a member does not have enough points for a voucher."""


def get_balance(user):
    return user.reward_transactions.aggregate(total=Sum('points_delta'))['total'] or 0


@transaction.atomic
def award_verified_pickup(user, kilograms, pickup_reference):
    """Award points for a verified pickup; a stable reference makes retries safe."""
    try:
        weight = Decimal(str(kilograms)).quantize(
            Decimal('0.1'),
            rounding=ROUND_DOWN,
        )
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('Berat limbah harus berupa angka yang valid.') from exc

    if not weight.is_finite() or weight <= 0:
        raise ValueError('Berat limbah harus lebih dari 0 kg.')
    if not pickup_reference:
        raise ValueError('Referensi penjemputan wajib diisi.')

    User = get_user_model()
    User.objects.select_for_update().get(pk=user.pk)

    existing = RewardTransaction.objects.filter(
        source_reference=pickup_reference,
        kind=RewardTransaction.Kind.PICKUP,
    ).first()
    if existing:
        if existing.user_id != user.pk:
            raise ValueError('Referensi penjemputan sudah digunakan mitra lain.')
        return existing

    points = int((weight * POINTS_PER_KILOGRAM).to_integral_value(rounding=ROUND_DOWN))
    balance = get_balance(user) + points
    return RewardTransaction.objects.create(
        user=user,
        kind=RewardTransaction.Kind.PICKUP,
        points_delta=points,
        balance_after=balance,
        weight_kg=weight,
        description=f'Setoran terverifikasi · {pickup_reference}',
        source_reference=pickup_reference,
    )


@transaction.atomic
def redeem_voucher(user, voucher_id):
    """Spend a member's points and issue a time-limited voucher atomically."""
    User = get_user_model()
    User.objects.select_for_update().get(pk=user.pk)

    voucher = RewardVoucher.objects.select_for_update().get(
        pk=voucher_id,
        is_active=True,
    )
    balance = get_balance(user)
    if balance < voucher.points_cost:
        raise InsufficientPoints

    new_balance = balance - voucher.points_cost
    user_voucher = UserVoucher.objects.create(
        user=user,
        voucher=voucher,
        points_spent=voucher.points_cost,
        expires_at=timezone.now() + timedelta(days=voucher.valid_days),
    )
    RewardTransaction.objects.create(
        user=user,
        kind=RewardTransaction.Kind.REDEMPTION,
        points_delta=-voucher.points_cost,
        balance_after=new_balance,
        description=f'Tukar voucher {voucher.value_label}',
    )
    return user_voucher
