from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from .models import RewardTransaction, RewardVoucher, UserVoucher
from .points import POINTS_PER_KILOGRAM, points_for_weight


class InsufficientPoints(Exception):
    """Raised when a member does not have enough points for a voucher."""


class VoucherUnavailable(Exception):
    """Raised when a member voucher is missing, expired, or already used."""


def _require_mitra(user):
    profile = getattr(user, 'userprofile', None)
    if (
        not getattr(user, 'is_authenticated', False)
        or not profile
        or profile.role != 'mitra'
    ):
        raise PermissionDenied('Fitur Waste & Reward hanya tersedia untuk mitra B2B.')


def get_balance(user):
    return user.reward_transactions.aggregate(total=Sum('points_delta'))['total'] or 0


@transaction.atomic
def award_verified_pickup(user, kilograms, pickup_reference):
    """Award points for a verified pickup; a stable reference makes retries safe."""
    _require_mitra(user)
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

    points = points_for_weight(weight)
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
    _require_mitra(user)
    User = get_user_model()
    User.objects.select_for_update().get(pk=user.pk)

    try:
        voucher = RewardVoucher.objects.select_for_update().get(
            pk=voucher_id,
            is_active=True,
        )
    except RewardVoucher.DoesNotExist as exc:
        raise VoucherUnavailable('Voucher tidak tersedia.') from exc
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


def _checkout_amount(value, field_name):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f'{field_name} harus berupa angka yang valid.') from exc

    if not amount.is_finite() or amount < 0:
        raise ValueError(f'{field_name} tidak boleh negatif.')
    return amount


def _label_amount(value_label):
    digits = ''.join(re.findall(r'\d', value_label))
    if not digits:
        raise ValueError('Nilai voucher tidak dapat dibaca.')
    return Decimal(digits)


@transaction.atomic
def apply_voucher_at_checkout(
    user,
    voucher_code,
    order_reference,
    subtotal,
    shipping_cost=0,
    wholesale_order=False,
):
    """Validate and consume a member voucher while calculating checkout totals.

    Call this inside the checkout's outer transaction together with order creation,
    so an invalid voucher rolls back the order as well.
    """
    _require_mitra(user)
    order_reference = str(order_reference or '').strip()
    if not order_reference:
        raise ValueError('Referensi pesanan wajib diisi.')
    if len(order_reference) > 80:
        raise ValueError('Referensi pesanan maksimal 80 karakter.')

    subtotal = _checkout_amount(subtotal, 'Subtotal')
    shipping_cost = _checkout_amount(shipping_cost, 'Ongkos kirim')

    try:
        user_voucher = UserVoucher.objects.select_for_update().select_related(
            'voucher'
        ).get(user=user, code=voucher_code)
    except UserVoucher.DoesNotExist as exc:
        raise VoucherUnavailable('Voucher tidak ditemukan untuk akun ini.') from exc

    current_time = timezone.now()
    if user_voucher.used_at is not None:
        raise VoucherUnavailable('Voucher ini sudah pernah digunakan.')
    if user_voucher.expires_at <= current_time:
        raise VoucherUnavailable('Masa berlaku voucher sudah habis.')
    if UserVoucher.objects.filter(used_order_reference=order_reference).exists():
        raise VoucherUnavailable('Pesanan ini sudah menggunakan voucher.')

    voucher = user_voucher.voucher
    goods_discount = Decimal('0')
    shipping_discount = Decimal('0')

    if voucher.kind == RewardVoucher.Kind.DISCOUNT:
        goods_discount = min(subtotal, _label_amount(voucher.value_label))
    elif voucher.kind == RewardVoucher.Kind.SHIPPING:
        shipping_discount = min(shipping_cost, _label_amount(voucher.value_label))
    elif voucher.kind == RewardVoucher.Kind.WHOLESALE:
        if not wholesale_order:
            raise VoucherUnavailable('Voucher ini hanya berlaku untuk pesanan grosir B2B.')
        match = re.search(r'\d+(?:[,.]\d+)?', voucher.value_label)
        if not match:
            raise ValueError('Persentase voucher tidak dapat dibaca.')
        percentage = Decimal(match.group().replace(',', '.'))
        goods_discount = (subtotal * percentage / Decimal('100')).quantize(
            Decimal('1'),
            rounding=ROUND_DOWN,
        )
    else:
        raise VoucherUnavailable('Jenis voucher ini belum dapat digunakan saat checkout.')

    total_due = subtotal - goods_discount + shipping_cost - shipping_discount
    user_voucher.used_at = current_time
    user_voucher.used_order_reference = order_reference
    try:
        with transaction.atomic():
            user_voucher.save(update_fields=('used_at', 'used_order_reference'))
    except IntegrityError as exc:
        raise VoucherUnavailable('Pesanan ini sudah menggunakan voucher.') from exc

    return {
        'user_voucher': user_voucher,
        'goods_discount': goods_discount,
        'shipping_discount': shipping_discount,
        'subtotal': subtotal,
        'shipping_cost': shipping_cost,
        'total_due': total_due,
    }
