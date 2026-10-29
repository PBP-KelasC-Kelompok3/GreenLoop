from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from accounts.decorator import role_required
from .points import POINTS_PER_KILOGRAM, membership_tier

from .models import RewardTransaction, RewardVoucher, UserVoucher
from .services import (
    InsufficientPoints,
    VoucherUnavailable,
    get_balance,
    redeem_voucher,
)


def _format_points(value):
    return f'{value:,}'.replace(',', '.')


@role_required(['mitra'])
def dashboard(request):
    balance = get_balance(request.user)
    query = request.GET.get('q', '').strip()

    level = membership_tier(balance)
    if level == 'Platinum':
        next_level, next_threshold = 'Platinum', 5000
    elif level == 'Gold':
        next_level, next_threshold = 'Platinum', 5000
    elif level == 'Silver':
        next_level, next_threshold = 'Gold', 3000
    else:
        next_level, next_threshold = 'Silver', 1000

    progress_start = {'Bronze': 0, 'Silver': 1000, 'Gold': 3000, 'Platinum': 5000}[level]
    progress = min(
        100,
        round((balance - progress_start) / max(1, next_threshold - progress_start) * 100),
    )

    transactions_query = RewardTransaction.objects.filter(user=request.user)
    vouchers_query = RewardVoucher.objects.filter(is_active=True)
    if query:
        transactions_query = transactions_query.filter(description__icontains=query)
        vouchers_query = vouchers_query.filter(
            Q(title__icontains=query)
            | Q(value_label__icontains=query)
            | Q(description__icontains=query)
        )

    vouchers = list(vouchers_query)
    for voucher in vouchers:
        voucher.can_redeem = balance >= voucher.points_cost
        voucher.points_cost_display = _format_points(voucher.points_cost)

    transactions = list(transactions_query[:8])
    for item in transactions:
        item.points_display = _format_points(abs(item.points_delta))
        item.balance_display = _format_points(item.balance_after)
        item.is_credit = item.points_delta >= 0
        item.weight_display = (
            f'{item.weight_kg:.1f} kg'.replace('.', ',')
            if item.weight_kg is not None
            else '—'
        )

    owned_query = UserVoucher.objects.filter(user=request.user)
    current_time = now()
    owned_vouchers = list(owned_query.select_related('voucher')[:4])
    for owned in owned_vouchers:
        owned.available = owned.used_at is None and owned.expires_at > current_time

    context = {
        'balance': _format_points(balance),
        'points_per_kg': POINTS_PER_KILOGRAM,
        'level': level,
        'next_level': next_level,
        'next_threshold': _format_points(next_threshold),
        'progress': progress,
        'points_to_next': _format_points(max(0, next_threshold - balance)),
        'vouchers': vouchers,
        'transactions': transactions,
        'owned_vouchers': owned_vouchers,
        'available_voucher_count': owned_query.filter(
            used_at__isnull=True,
            expires_at__gt=current_time,
        ).count(),
        'initials': (request.user.get_full_name() or request.user.username)[:2].upper(),
    }
    return render(request, 'waste_reward/dashboard.html', context)


@require_POST
@role_required(['mitra'])
def redeem(request, voucher_id):
    voucher = get_object_or_404(RewardVoucher, pk=voucher_id, is_active=True)
    try:
        redeem_voucher(request.user, voucher.pk)
    except InsufficientPoints:
        messages.error(request, 'Poin kamu belum cukup untuk menukar voucher ini.')
    except VoucherUnavailable as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'Voucher {voucher.value_label} berhasil ditambahkan.')
    return redirect('waste_reward:dashboard')
