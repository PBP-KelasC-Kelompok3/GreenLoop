import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from accounts.permissions import can_manage_greenloop
from waste_reward.models import UserVoucher
from waste_reward.services import VoucherUnavailable, apply_voucher_at_checkout

from .forms import CheckoutForm, ProductForm
from .models import Order, OrderItem, Product
from .services import (
    ServiceError,
    calculate_shipping as get_shipping_options,
    create_snap_token,
    fetch_transaction_status,
    search_destinations,
    snap_js_url,
    valid_notification_signature,
)


def is_mitra(role):
    return role == "mitra"


def _user_is_mitra(user):
    profile = getattr(user, "userprofile", None) if user.is_authenticated else None
    return bool(profile and is_mitra(profile.role))


def _is_catalog_admin(user):
    return can_manage_greenloop(user)


def _can_shop(user):
    profile = getattr(user, "userprofile", None) if user.is_authenticated else None
    return bool(profile and profile.role in ("consumer", "mitra") and not _is_catalog_admin(user))


def _unit_price(user, product):
    return product.price_b2b if _user_is_mitra(user) else product.price_b2c


def _cart(request):
    raw_cart = request.session.get("catalog_cart", {})
    products = Product.objects.filter(pk__in=[key for key in raw_cart if str(key).isdigit()])
    lines = []
    clean_cart = {}
    subtotal = 0
    weight_grams = 0
    for product in products:
        try:
            quantity = int(raw_cart.get(str(product.pk), raw_cart.get(product.pk, 0)))
        except (TypeError, ValueError):
            continue
        if quantity <= 0 or product.stock <= 0:
            continue
        quantity = min(quantity, product.stock, 99)
        clean_cart[str(product.pk)] = quantity
        unit_price = _unit_price(request.user, product)
        line_total = unit_price * quantity
        lines.append({
            "product": product,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": line_total,
        })
        subtotal += line_total
        weight_grams += product.weight_grams * quantity
    if clean_cart != raw_cart:
        request.session["catalog_cart"] = clean_cart
    return {
        "items": lines,
        "subtotal": subtotal,
        "weight_grams": weight_grams,
        "count": sum(line["quantity"] for line in lines),
    }


def _page_context(request, **extra):
    context = {
        "cart_count": _cart(request)["count"] if _can_shop(request.user) else 0,
        "is_mitra": _user_is_mitra(request.user),
        "is_admin": _is_catalog_admin(request.user),
        "can_shop": _can_shop(request.user),
        "is_authenticated": request.user.is_authenticated,
        "midtrans_client_key": settings.MIDTRANS_CLIENT_KEY,
        "snap_js_url": snap_js_url(),
    }
    context.update(extra)
    return context


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return None


def katalog_page(request):
    if _is_catalog_admin(request.user):
        return redirect("katalog:admin_products")
    return render(request, "catalog/katalog.html", _page_context(request))


@login_required
def admin_products_page(request):
    if not _is_catalog_admin(request.user):
        return HttpResponseForbidden("Halaman ini hanya untuk Admin.")
    products = Product.objects.order_by("name")
    product_rows = [{"product": product, "form": ProductForm(instance=product)} for product in products]
    return render(request, "catalog/admin_products.html", {
        "product_rows": product_rows,
        "form": ProductForm(),
    })


@login_required
@require_POST
def add_admin_product(request):
    if not _is_catalog_admin(request.user):
        return HttpResponseForbidden("Hanya Admin yang dapat menambah produk.")
    form = ProductForm(request.POST, request.FILES)
    if form.is_valid():
        product = form.save()
        messages.success(request, f"Produk {product.name} berhasil ditambahkan ke katalog.")
    else:
        messages.error(request, "Produk belum tersimpan. Periksa kembali semua field dan foto.")
    return redirect("katalog:admin_products")


@login_required
@require_POST
def update_admin_product(request, product_id):
    if not _is_catalog_admin(request.user):
        return HttpResponseForbidden("Hanya Admin yang dapat mengubah produk.")
    product = get_object_or_404(Product, pk=product_id)
    form = ProductForm(request.POST, request.FILES, instance=product)
    if form.is_valid():
        form.save()
        messages.success(request, f"Produk {product.name} berhasil diperbarui.")
    else:
        messages.error(request, f"Produk {product.name} belum berubah. Periksa kembali field dan foto.")
    return redirect("katalog:admin_products")


@login_required
@require_POST
def delete_admin_product(request, product_id):
    if not _is_catalog_admin(request.user):
        return HttpResponseForbidden("Hanya Admin yang dapat menghapus produk.")
    product = get_object_or_404(Product, pk=product_id)
    product_name = product.name
    image_name = product.image.name if product.image else None
    image_storage = product.image.storage if product.image else None
    product.delete()
    if image_name:
        image_storage.delete(image_name)
    messages.success(request, f"Produk {product_name} berhasil dihapus.")
    return redirect("katalog:admin_products")


def catalog_preview(request):
    if not _is_catalog_admin(request.user):
        return HttpResponseForbidden("Pratinjau katalog ini hanya tersedia untuk Admin.")
    return render(request, "catalog/admin_preview.html", _page_context(
        request,
        is_admin=True,
        is_preview=True,
        is_mitra=False,
        can_shop=False,
    ))


def product_detail_preview(request, product_id):
    if not _is_catalog_admin(request.user):
        return HttpResponseForbidden("Pratinjau produk ini hanya tersedia untuk Admin.")
    product = get_object_or_404(Product, pk=product_id)
    return render(request, "catalog/admin_preview_detail.html", _page_context(
        request,
        product=product,
        price=product.price_b2c,
        is_admin=True,
        is_preview=True,
        is_mitra=False,
        can_shop=False,
    ))


def product_detail(request, product_id):
    if _is_catalog_admin(request.user):
        return redirect("katalog:admin_products")
    product = get_object_or_404(Product, pk=product_id)
    return render(request, "catalog/product_detail.html", _page_context(
        request,
        product=product,
        price=_unit_price(request.user, product),
        form=ProductForm(),
        is_admin=_is_catalog_admin(request.user),
    ))


@login_required
def cart_page(request):
    if not _can_shop(request.user):
        return redirect("admin_dashboard") if _is_catalog_admin(request.user) else HttpResponseForbidden("Silakan masuk sebagai konsumen atau Mitra untuk berbelanja.")
    cart = _cart(request)
    return render(request, "catalog/cart.html", _page_context(request, **cart))


@login_required
def checkout_page(request):
    if not _can_shop(request.user):
        return redirect("admin_dashboard") if _is_catalog_admin(request.user) else HttpResponseForbidden("Silakan masuk sebagai konsumen atau Mitra untuk checkout.")
    cart = _cart(request)
    if not cart["items"]:
        messages.info(request, "Tambahkan produk ke keranjang sebelum checkout.")
        return redirect("katalog:cart")
    return render(request, "catalog/checkout.html", _page_context(
        request,
        **cart,
        form=CheckoutForm(),
        vouchers=UserVoucher.objects.filter(
            user=request.user,
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).select_related("voucher") if _user_is_mitra(request.user) else [],
    ))


@login_required
def admin_orders_page(request):
    if not _is_catalog_admin(request.user):
        return HttpResponseForbidden("Halaman ini hanya untuk Admin.")
    orders = Order.objects.select_related("user").prefetch_related("items").order_by("-created_at")
    for order in orders:
        order.next_admin_status = {"PAID": "PROCESSING", "PROCESSING": "SHIPPED", "SHIPPED": "DELIVERED"}.get(order.status, "")
    return render(request, "catalog/admin_orders.html", _page_context(request, orders=orders))


@login_required
@require_POST
def update_admin_order(request, order_id):
    if not _is_catalog_admin(request.user):
        return HttpResponseForbidden("Hanya Admin yang dapat memperbarui pesanan.")
    order = get_object_or_404(Order, order_id=order_id)
    new_status = request.POST.get("status", order.status)
    tracking_number = request.POST.get("tracking_number", "").strip()
    allowed_next = {"PAID": "PROCESSING", "PROCESSING": "SHIPPED", "SHIPPED": "DELIVERED"}
    if new_status != order.status and allowed_next.get(order.status) != new_status:
        messages.error(request, "Status pesanan hanya dapat maju sesuai urutan proses.")
        return redirect("katalog:admin_orders")
    if new_status not in (order.status, "PROCESSING", "SHIPPED", "DELIVERED"):
        messages.error(request, "Status pembayaran atau pesanan ini tidak dapat diubah dari halaman ini.")
        return redirect("katalog:admin_orders")
    order.status = new_status
    order.tracking_number = tracking_number
    order.save(update_fields=["status", "tracking_number"])
    messages.success(request, f"Pesanan {order.order_id[:12]} berhasil diperbarui.")
    return redirect("katalog:admin_orders")


@login_required
def orders_page(request):
    if not _can_shop(request.user):
        return redirect("admin_dashboard") if _is_catalog_admin(request.user) else HttpResponseForbidden("Halaman pesanan hanya untuk konsumen dan Mitra.")
    orders = Order.objects.filter(user=request.user).prefetch_related("items").order_by("-created_at")
    return render(request, "catalog/orders.html", _page_context(request, orders=orders))


@login_required
def order_tracking(request, order_id):
    if not _can_shop(request.user):
        return redirect("admin_dashboard") if _is_catalog_admin(request.user) else HttpResponseForbidden("Halaman pesanan hanya untuk konsumen dan Mitra.")
    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        order_id=order_id,
        user=request.user,
    )
    steps = [
        ("Pesanan dibuat", True),
        ("Pembayaran berhasil", order.payment_status == Order.PaymentStatus.PAID),
        ("Pesanan disiapkan", order.status in ("PROCESSING", "SHIPPED", "DELIVERED")),
        ("Diserahkan ke kurir", order.status in ("SHIPPED", "DELIVERED")),
        ("Pesanan diterima", order.status == "DELIVERED"),
    ]
    return render(request, "catalog/order_tracking.html", _page_context(
        request,
        order=order,
        steps=steps,
    ))


@require_GET
def get_products(request):
    search = request.GET.get("search", "").strip()
    products = Product.objects.filter(name__icontains=search).order_by("name")
    is_user_mitra = _user_is_mitra(request.user)
    data = []
    for product in products:
        item = {
            "id": product.pk,
            "name": product.name,
            "description": product.description,
            "image_url": product.image.url if product.image else None,
            "price": _unit_price(request.user, product),
            "stock": product.stock,
            "weight_grams": product.weight_grams,
            "detail_url": reverse("katalog:product_detail", args=[product.pk]),
        }
        if _is_catalog_admin(request.user):
            item["price_b2c"] = product.price_b2c
            item["price_b2b"] = product.price_b2b
        data.append(item)
    return JsonResponse({"products": data, "is_mitra": is_user_mitra})


@csrf_exempt
@require_POST
def add_product(request):
    if not _is_catalog_admin(request.user):
        return HttpResponseForbidden("Hanya Admin yang dapat menambah produk.")
    form = ProductForm(request.POST, request.FILES)
    if form.is_valid():
        form.save()
        return JsonResponse({"status": "created"}, status=201)
    return JsonResponse({"status": "error", "errors": form.errors}, status=400)


@csrf_exempt
@require_POST
def edit_product(request, id):
    if not _is_catalog_admin(request.user):
        return HttpResponseForbidden("Hanya Admin yang dapat mengedit produk.")
    product = get_object_or_404(Product, pk=id)
    form = ProductForm(request.POST, request.FILES, instance=product)
    if form.is_valid():
        form.save()
        return JsonResponse({"status": "updated"})
    return JsonResponse({"status": "error", "errors": form.errors}, status=400)


@login_required
@require_POST
def add_to_cart(request):
    if not _can_shop(request.user):
        return HttpResponseForbidden("Admin tidak dapat berbelanja. Masuk sebagai konsumen atau Mitra.")
    body = _json_body(request)
    if body is None:
        return JsonResponse({"error": "Data permintaan tidak valid."}, status=400)
    product = get_object_or_404(Product, pk=body.get("product_id"))
    try:
        quantity = int(body.get("quantity", 1))
    except (TypeError, ValueError):
        return JsonResponse({"error": "Jumlah produk tidak valid."}, status=400)
    if quantity < 1 or quantity > 99:
        return JsonResponse({"error": "Jumlah harus antara 1 dan 99."}, status=400)
    cart = request.session.get("catalog_cart", {})
    current = int(cart.get(str(product.pk), 0))
    if product.stock < current + quantity:
        return JsonResponse({"error": "Jumlah melebihi stok yang tersedia."}, status=400)
    cart[str(product.pk)] = current + quantity
    request.session["catalog_cart"] = cart
    return JsonResponse({"count": sum(cart.values()), "cart_url": reverse("katalog:cart")})


@login_required
@require_POST
def update_cart_item(request, product_id):
    if not _can_shop(request.user):
        return HttpResponseForbidden("Admin tidak dapat berbelanja. Masuk sebagai konsumen atau Mitra.")
    body = _json_body(request)
    if body is None:
        return JsonResponse({"error": "Data permintaan tidak valid."}, status=400)
    cart = request.session.get("catalog_cart", {})
    key = str(product_id)
    if body.get("remove"):
        cart.pop(key, None)
    else:
        product = get_object_or_404(Product, pk=product_id)
        try:
            quantity = int(body.get("quantity", 1))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Jumlah produk tidak valid."}, status=400)
        if quantity <= 0:
            cart.pop(key, None)
        elif quantity > min(product.stock, 99):
            return JsonResponse({"error": "Jumlah melebihi stok yang tersedia."}, status=400)
        else:
            cart[key] = quantity
    request.session["catalog_cart"] = cart
    return JsonResponse({"count": sum(cart.values()), "cart_url": reverse("katalog:cart")})


@login_required
@require_GET
def search_destinations_api(request):
    if not _can_shop(request.user):
        return HttpResponseForbidden("Checkout hanya tersedia untuk konsumen dan Mitra.")
    try:
        destinations = search_destinations(request.GET.get("q", ""))
    except ServiceError as error:
        return JsonResponse({"error": str(error)}, status=502)
    return JsonResponse({"destinations": destinations})


@login_required
@require_POST
def calculate_shipping_api(request):
    if not _can_shop(request.user):
        return HttpResponseForbidden("Checkout hanya tersedia untuk konsumen dan Mitra.")
    body = _json_body(request)
    cart = _cart(request)
    if body is None or not cart["items"]:
        return JsonResponse({"error": "Keranjang kosong atau permintaan tidak valid."}, status=400)
    destination_id = str(body.get("destination_id", ""))
    if not destination_id.isdigit():
        return JsonResponse({"error": "Pilih tujuan pengiriman yang tersedia."}, status=400)
    try:
        options = get_shipping_options(destination_id, cart["weight_grams"])
    except ServiceError as error:
        return JsonResponse({"error": str(error)}, status=502)
    return JsonResponse({"options": options, "weight_grams": cart["weight_grams"]})


@login_required
@require_POST
def create_order(request):
    if not _can_shop(request.user):
        return HttpResponseForbidden("Admin tidak dapat membuat pesanan. Masuk sebagai konsumen atau Mitra.")
    form = CheckoutForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"error": "Periksa kembali data penerima dan pengiriman."}, status=400)
    cart = _cart(request)
    if not cart["items"]:
        return JsonResponse({"error": "Keranjang kosong."}, status=400)
    data = form.cleaned_data
    try:
        shipping_options = get_shipping_options(data["destination_id"], cart["weight_grams"])
    except ServiceError as error:
        return JsonResponse({"error": str(error)}, status=502)
    selected = next((option for option in shipping_options if
        option["courier_code"].casefold() == data["courier_code"].casefold()
        and option["service"] == data["courier_service"]), None)
    if selected is None:
        return JsonResponse({"error": "Pilihan ongkir berubah. Hitung ulang ongkir lalu pilih kurir."}, status=400)

    locked_products = {}
    try:
        with transaction.atomic():
            for line in cart["items"]:
                product = Product.objects.select_for_update().get(pk=line["product"].pk)
                if product.stock < line["quantity"]:
                    return JsonResponse({"error": f"Stok {product.name} tidak mencukupi."}, status=409)
                locked_products[product.pk] = product
            first = cart["items"][0]
            order = Order.objects.create(
                user=request.user,
                product=locked_products[first["product"].pk],
                subtotal=cart["subtotal"],
                shipping_cost=selected["cost"],
                total_amount=cart["subtotal"] + selected["cost"],
                recipient_name=data["recipient_name"],
                phone=data["phone"],
                shipping_address=data["shipping_address"],
                destination_id=data["destination_id"],
                destination_label=data["destination_label"],
                courier_code=selected["courier_code"],
                courier_name=selected["courier_name"],
                courier_service=selected["service"],
                shipping_eta=selected["etd"],
                stock_reserved=True,
            )
            voucher_code = data.get("voucher_code", "").strip()
            if voucher_code:
                if not _user_is_mitra(request.user):
                    raise VoucherUnavailable("Voucher Waste Points hanya tersedia untuk Mitra B2B.")
                voucher_result = apply_voucher_at_checkout(
                    request.user,
                    voucher_code,
                    order.order_id,
                    cart["subtotal"],
                    selected["cost"],
                    wholesale_order=cart["count"] >= 24,
                )
                order.user_voucher = voucher_result["user_voucher"]
                order.goods_discount = int(voucher_result["goods_discount"])
                order.shipping_discount = int(voucher_result["shipping_discount"])
                order.total_amount = int(voucher_result["total_due"])
                order.save(update_fields=["user_voucher", "goods_discount", "shipping_discount", "total_amount"])
            order_items = []
            for line in cart["items"]:
                product = locked_products[line["product"].pk]
                order_items.append(OrderItem(
                    order=order,
                    product=product,
                    product_name=product.name,
                    unit_price=_unit_price(request.user, product),
                    quantity=line["quantity"],
                ))
                product.stock -= line["quantity"]
                product.save(update_fields=["stock"])
            OrderItem.objects.bulk_create(order_items)
            order.snap_token = create_snap_token(order)
            order.save(update_fields=["snap_token"])
    except ServiceError as error:
        return JsonResponse({"error": str(error)}, status=502)
    except (VoucherUnavailable, ValueError) as error:
        return JsonResponse({"error": str(error)}, status=400)

    request.session["catalog_cart"] = {}
    return JsonResponse({
        "order_url": reverse("katalog:order_tracking", args=[order.order_id]),
        "snap_token": order.snap_token,
        "total_amount": order.total_amount,
    }, status=201)


def _apply_payment_status(order, payload):
    status = payload.get("transaction_status")
    fraud_status = payload.get("fraud_status")
    if status in ("settlement", "capture") and (status != "capture" or fraud_status == "accept"):
        order.payment_status = Order.PaymentStatus.PAID
        if order.status == "PENDING":
            order.status = "PAID"
        order.stock_reserved = False
    elif status in ("expire", "cancel", "deny"):
        if order.payment_status == Order.PaymentStatus.PENDING and order.stock_reserved:
            for item in order.items.select_related("product"):
                if item.product_id:
                    Product.objects.filter(pk=item.product_id).update(stock=F("stock") + item.quantity)
            order.stock_reserved = False
            order.payment_status = Order.PaymentStatus.FAILED
            order.status = "CANCELLED"
            if order.user_voucher_id:
                voucher = UserVoucher.objects.select_for_update().filter(pk=order.user_voucher_id).first()
                if voucher and voucher.used_order_reference == order.order_id:
                    voucher.used_at = None
                    voucher.used_order_reference = None
                    voucher.save(update_fields=["used_at", "used_order_reference"])
    elif status in ("refund", "partial_refund"):
        order.payment_status = Order.PaymentStatus.REFUNDED
    order.save(update_fields=["payment_status", "status", "stock_reserved"])


@csrf_exempt
@require_POST
def midtrans_notification(request):
    payload = _json_body(request)
    if not payload or not valid_notification_signature(payload):
        return JsonResponse({"error": "Invalid notification signature."}, status=403)
    with transaction.atomic():
        order = Order.objects.select_for_update().filter(order_id=payload.get("order_id")).first()
        if order is None:
            return JsonResponse({"error": "Order not found."}, status=404)
        _apply_payment_status(order, payload)
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def refresh_order_payment(request, order_id):
    if not _can_shop(request.user):
        return HttpResponseForbidden("Halaman pesanan hanya untuk konsumen dan Mitra.")
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    if order.payment_status == Order.PaymentStatus.PENDING:
        try:
            payload = fetch_transaction_status(order.order_id)
        except ServiceError as error:
            return JsonResponse({"error": str(error)}, status=502)
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            _apply_payment_status(order, payload)
    return JsonResponse({"payment_status": order.payment_status, "status": order.status})


@login_required
@require_GET
def get_orders(request):
    if not _can_shop(request.user):
        return HttpResponseForbidden("Halaman pesanan hanya untuk konsumen dan Mitra.")
    orders = Order.objects.filter(user=request.user).prefetch_related("items").order_by("-created_at")
    data = [{
        "order_id": order.order_id,
        "amount": order.total_amount,
        "status": order.get_status_display(),
        "payment_status": order.get_payment_status_display(),
        "tracking_url": reverse("katalog:order_tracking", args=[order.order_id]),
        "products": [{"name": item.product_name, "quantity": item.quantity} for item in order.items.all()],
    } for order in orders]
    return JsonResponse(data, safe=False)
