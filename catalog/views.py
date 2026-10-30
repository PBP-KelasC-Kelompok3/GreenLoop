import json
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from accounts.models import UserProfile
from accounts.permissions import can_manage_greenloop
from waste_reward.models import UserVoucher
from waste_reward.services import (
    VoucherUnavailable,
    apply_voucher_at_checkout,
    get_balance,
)

from .forms import ProductForm
from .models import Order, Product
from .services import (
    ServiceError,
    calculate_shipping as get_shipping_options,
    create_snap_token,
    fetch_transaction_status,
    search_destinations,
    snap_js_url,
    valid_notification_signature,
)


def _is_mitra(user):
    try:
        profile = user.userprofile if user.is_authenticated else None
    except (AttributeError, UserProfile.DoesNotExist):
        profile = None
    return bool(profile and profile.role == 'mitra')


def _json_body(request):
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError('Format data tidak valid.') from exc
    if not isinstance(body, dict):
        raise ValueError('Format data tidak valid.')
    return body


def _error(message, status=400):
    return JsonResponse({'error': str(message)}, status=status)


@ensure_csrf_cookie
@require_GET
def katalog_page(request):
    is_mitra = _is_mitra(request.user)
    owned_vouchers = UserVoucher.objects.none()
    if is_mitra:
        owned_vouchers = UserVoucher.objects.filter(
            user=request.user,
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).select_related('voucher').order_by('expires_at')
    return render(request, 'catalog/katalog.html', {
        'midtrans_client_key': settings.MIDTRANS_CLIENT_KEY or '',
        'snap_js_url': snap_js_url(),
        'is_admin': can_manage_greenloop(request.user),
        'is_mitra': is_mitra,
        'reward_balance': get_balance(request.user) if is_mitra else 0,
        'owned_vouchers': owned_vouchers,
        'form': ProductForm(),
    })


@require_GET
def get_products(request):
    search = request.GET.get('search', '').strip()[:100]
    mitra = _is_mitra(request.user)
    products = Product.objects.filter(name__icontains=search).order_by('name')
    return JsonResponse([
        {
            'id': item.pk,
            'name': item.name,
            'description': item.description,
            'price': item.price_b2b if mitra else item.price_b2c,
            'price_b2b': item.price_b2b,
            'price_b2c': item.price_b2c,
            'stock': item.stock,
            'weight_grams': item.weight_grams,
        }
        for item in products
    ], safe=False)


@login_required
@require_POST
def add_product(request):
    if not can_manage_greenloop(request.user):
        raise PermissionDenied('Hanya admin GreenLoop yang dapat menambah produk.')
    form = ProductForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    product = form.save()
    return JsonResponse({'status': 'created', 'id': product.pk}, status=201)


@login_required
@require_POST
def edit_product(request, id):
    if not can_manage_greenloop(request.user):
        raise PermissionDenied('Hanya admin GreenLoop yang dapat mengedit produk.')
    product = get_object_or_404(Product, pk=id)
    form = ProductForm(request.POST, instance=product)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    form.save()
    return JsonResponse({'status': 'updated'})


@require_GET
def find_destinations(request):
    term = request.GET.get('q', '').strip()[:80]
    if len(term) < 3:
        return JsonResponse({'results': []})
    try:
        return JsonResponse({'results': search_destinations(term)})
    except ServiceError as exc:
        return _error(exc, 503)


@require_POST
def calculate_shipping(request):
    try:
        body = _json_body(request)
        destination_id = str(body.get('destination_id', '')).strip()
        weight_grams = int(body.get('weight_grams', 1000))
        if not destination_id or weight_grams <= 0:
            raise ValueError('Pilih tujuan dan masukkan berat produk yang valid.')
        options = get_shipping_options(destination_id, weight_grams)
    except (TypeError, ValueError) as exc:
        return _error(exc)
    except ServiceError as exc:
        return _error(exc, 503)
    return JsonResponse({'options': options})


def _release_order_reservations(order):
    if order.product_id:
        Product.objects.filter(pk=order.product_id).update(
            stock=F('stock') + order.quantity
        )
    if order.voucher_id:
        user_voucher = order.voucher
        if user_voucher.used_order_reference == order.order_id:
            user_voucher.used_at = None
            user_voucher.used_order_reference = None
            user_voucher.save(update_fields=('used_at', 'used_order_reference'))


def _sync_payment_status(order, provider_status):
    status = provider_status.get('transaction_status')
    fraud = provider_status.get('fraud_status')
    try:
        amount_matches = Decimal(str(
            provider_status.get('gross_amount', order.total_amount)
        )) == Decimal(order.total_amount)
    except (InvalidOperation, TypeError, ValueError):
        amount_matches = False

    if status == 'capture' and fraud not in (None, 'accept'):
        return order
    if status in ('settlement', 'capture'):
        if amount_matches and order.status != 'CANCELLED':
            order.status = 'PAID'
            order.save(update_fields=('status',))
    elif status in ('deny', 'cancel', 'expire', 'failure') and order.status == 'PENDING':
        _release_order_reservations(order)
        order.status = 'CANCELLED'
        order.save(update_fields=('status',))
    return order


@login_required
@require_POST
def create_transaction(request):
    if not settings.MIDTRANS_CLIENT_KEY or not settings.MIDTRANS_SERVER_KEY:
        return _error('Pembayaran belum dikonfigurasi oleh admin GreenLoop.', 503)
    try:
        body = _json_body(request)
        product_id = int(body.get('product_id'))
        quantity = int(body.get('quantity', 1))
        destination_id = str(body.get('destination_id', '')).strip()
        courier_code = str(body.get('courier_code', '')).strip().lower()
        courier_service = str(body.get('courier_service', '')).strip()
        recipient_name = str(body.get('recipient_name', '')).strip()
        phone = str(body.get('phone', '')).strip()
        address = str(body.get('address', '')).strip()
        voucher_code = str(body.get('voucher_code', '')).strip().upper()
        if quantity < 1 or quantity > 50:
            raise ValueError('Jumlah produk harus antara 1 dan 50.')
        if not all((destination_id, courier_code, courier_service,
                    recipient_name, phone, address)):
            raise ValueError('Lengkapi tujuan, jasa kirim, nama, telepon, dan alamat.')

        product = get_object_or_404(Product, pk=product_id)
        if product.stock < quantity:
            raise ValueError('Stok produk tidak mencukupi.')
        is_mitra = _is_mitra(request.user)
        unit_price = product.price_b2b if is_mitra else product.price_b2c
        subtotal = unit_price * quantity

        shipping_options = get_shipping_options(
            destination_id,
            product.weight_grams * quantity,
        )
        shipping = next((item for item in shipping_options if (
            item['courier_code'].lower() == courier_code
            and item['service'] == courier_service
        )), None)
        if shipping is None:
            raise ValueError('Opsi pengiriman berubah. Hitung ulang ongkir.')

        with transaction.atomic():
            stock_reserved = Product.objects.filter(
                pk=product_id, stock__gte=quantity
            ).update(stock=F('stock') - quantity)
            if not stock_reserved:
                raise ValueError('Stok produk tidak mencukupi.')
            product.refresh_from_db()
            order = Order.objects.create(
                user=request.user,
                product=product,
                product_name=product.name,
                quantity=quantity,
                unit_price=unit_price,
                subtotal=subtotal,
                shipping_cost=shipping['cost'],
                total_amount=subtotal + shipping['cost'],
                recipient_name=recipient_name[:100],
                phone=phone[:20],
                address=address[:2000],
                destination_id=destination_id[:30],
                courier_code=shipping['courier_code'][:20],
                courier_service=shipping['service'][:80],
            )

            if voucher_code:
                result = apply_voucher_at_checkout(
                    user=request.user,
                    voucher_code=voucher_code,
                    order_reference=order.order_id,
                    subtotal=subtotal,
                    shipping_cost=shipping['cost'],
                    wholesale_order=is_mitra,
                )
                order.voucher = result['user_voucher']
                order.goods_discount = int(result['goods_discount'])
                order.shipping_discount = int(result['shipping_discount'])
                order.total_amount = int(result['total_due'])
                order.save(update_fields=(
                    'voucher', 'goods_discount', 'shipping_discount', 'total_amount'
                ))

            if order.total_amount:
                order.payment_token = create_snap_token(order, request.user.email)
            else:
                order.status = 'PAID'
            order.save(update_fields=('payment_token', 'status'))
    except (TypeError, ValueError, VoucherUnavailable) as exc:
        return _error(exc)
    except ServiceError as exc:
        return _error(exc, 503)

    return JsonResponse({
        'token': order.payment_token,
        'order_id': order.order_id,
        'amount': order.total_amount,
        'goods_discount': order.goods_discount,
        'shipping_discount': order.shipping_discount,
    }, status=201)


@login_required
@require_POST
def confirm_payment(request):
    try:
        body = _json_body(request)
        order = get_object_or_404(
            Order, user=request.user, order_id=body.get('order_id')
        )
        provider_status = fetch_transaction_status(order.order_id)
    except ValueError as exc:
        return _error(exc)
    except ServiceError as exc:
        return _error(exc, 503)
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        _sync_payment_status(order, provider_status)
    return JsonResponse({'order_id': order.order_id, 'status': order.status})


@csrf_exempt
@require_POST
def payment_notification(request):
    try:
        payload = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error('Notifikasi pembayaran tidak valid.')
    if not isinstance(payload, dict) or not valid_notification_signature(payload):
        return _error('Tanda tangan pembayaran tidak valid.', 403)
    try:
        with transaction.atomic():
            order = Order.objects.select_for_update().get(
                order_id=payload.get('order_id', '')
            )
            _sync_payment_status(order, payload)
    except Order.DoesNotExist:
        return _error('Pesanan tidak ditemukan.', 404)
    return JsonResponse({'status': 'ok'})


@login_required
@require_GET
def get_orders(request):
    orders = Order.objects.filter(user=request.user).select_related(
        'product', 'voucher'
    ).order_by('-created_at')
    return JsonResponse([
        {
            'order_id': order.order_id,
            'product': order.product_name or (
                order.product.name if order.product_id else 'Produk dihapus'
            ),
            'quantity': order.quantity,
            'amount': order.total_amount,
            'status': order.get_status_display(),
            'voucher_code': order.voucher.code if order.voucher_id else '',
        }
        for order in orders
    ], safe=False)
