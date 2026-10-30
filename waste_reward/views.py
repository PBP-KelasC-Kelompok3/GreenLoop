from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.timezone import now
from django.views.decorators.http import require_POST

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


def reward_rate_limit(max_requests=10, window_seconds=60):
    """Cap voucher-redemption attempts per authenticated mitra in a short window."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            key = f'waste_reward:redeem:{request.user.pk}'
            if cache.add(key, 1, timeout=window_seconds):
                attempts = 1
            else:
                try:
                    attempts = cache.incr(key)
                except ValueError:
                    cache.set(key, 1, timeout=window_seconds)
                    attempts = 1

            if attempts > max_requests:
                message = 'Terlalu banyak percobaan. Coba lagi dalam satu menit.'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'error': message}, status=429)
                messages.error(request, message)
                return redirect('waste_reward:dashboard')
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def mitra_required(view_func):
    """Require an authenticated mitra and return a real 403 for other roles."""
    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        try:
            profile = request.user.userprofile
        except (AttributeError, ObjectDoesNotExist):
            profile = None
        if profile is None or profile.role != 'mitra':
            raise PermissionDenied('Waste & Reward hanya dapat diakses oleh mitra B2B.')
        return view_func(request, *args, **kwargs)

    return wrapped


@mitra_required
def dashboard(request):
    balance = get_balance(request.user)
    query = request.GET.get('q', '').strip()[:100]

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
    progress = 100 if level == 'Platinum' else min(
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

    transaction_kind = request.GET.get('kind', '')
    if transaction_kind in RewardTransaction.Kind.values:
        transactions_query = transactions_query.filter(kind=transaction_kind)
    else:
        transaction_kind = ''

    period = request.GET.get('period', 'all')
    if period in {'30', '90'}:
        transactions_query = transactions_query.filter(
            created_at__gte=now() - timedelta(days=int(period))
        )
    else:
        period = 'all'

    transaction_page = Paginator(
        transactions_query.select_related('user'), 10
    ).get_page(request.GET.get('page'))
    transactions = list(transaction_page.object_list)
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
        'balance_value': balance,
        'balance': _format_points(balance),
        'points_per_kg': POINTS_PER_KILOGRAM,
        'level': level,
        'next_level': next_level,
        'next_threshold': _format_points(next_threshold),
        'progress': progress,
        'points_to_next': _format_points(max(0, next_threshold - balance)),
        'vouchers': vouchers,
        'transactions': transactions,
        'transaction_page': transaction_page,
        'transaction_kind': transaction_kind,
        'transaction_period': period,
        'query_without_page': request.GET.copy(),
        'owned_vouchers': owned_vouchers,
        'available_voucher_count': owned_query.filter(
            used_at__isnull=True,
            expires_at__gt=current_time,
        ).count(),
        'initials': (request.user.get_full_name() or request.user.username)[:2].upper(),
    }
    context['query_without_page'].pop('page', None)
    return render(request, 'waste_reward/dashboard.html', context)


@mitra_required
@require_POST
@reward_rate_limit(max_requests=10, window_seconds=60)
def redeem(request, voucher_id):
    voucher = get_object_or_404(RewardVoucher, pk=voucher_id, is_active=True)
    try:
        owned = redeem_voucher(request.user, voucher.pk)
    except InsufficientPoints:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'error': 'Poin kamu belum cukup untuk menukar voucher ini.'}, status=409)
        messages.error(request, 'Poin kamu belum cukup untuk menukar voucher ini.')
    except VoucherUnavailable as exc:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'error': str(exc)}, status=409)
        messages.error(request, str(exc))
    else:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            balance = get_balance(request.user)
            level = membership_tier(balance)
            next_level, next_threshold = {
                'Bronze': ('Silver', 1000),
                'Silver': ('Gold', 3000),
                'Gold': ('Platinum', 5000),
                'Platinum': ('Platinum', 5000),
            }[level]
            progress_start = {'Bronze': 0, 'Silver': 1000, 'Gold': 3000, 'Platinum': 5000}[level]
            progress = 100 if level == 'Platinum' else min(100, round(
                (balance - progress_start) / max(1, next_threshold - progress_start) * 100
            ))
            return JsonResponse({
                'status': 'redeemed',
                'balance': balance,
                'balance_display': _format_points(balance),
                'level': level,
                'next_level': next_level,
                'next_threshold': _format_points(next_threshold),
                'points_to_next': _format_points(max(0, next_threshold - balance)),
                'progress': progress,
                'is_max_level': level == 'Platinum',
                'voucher': {
                    'code': owned.code,
                    'title': owned.voucher.title,
                    'value_label': owned.voucher.value_label,
                    'expires_at': owned.expires_at.isoformat(),
                    'expires_display': owned.expires_at.strftime('%d %b %Y'),
                },
                'transaction': {
                    'description': f'Tukar voucher {owned.voucher.value_label}',
                    'points_spent': owned.points_spent,
                    'points_display': _format_points(owned.points_spent),
                },
            })
        messages.success(request, f'Voucher {voucher.value_label} berhasil ditambahkan.')
    return redirect('waste_reward:dashboard')
