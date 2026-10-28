import json, requests, midtransclient
from django.shortcuts import render
from django.http import JsonResponse, HttpResponseForbidden
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from .models import Product, Order
from .forms import ProductForm
from accounts.models import UserProfile

def is_mitra(role):
    return role == "mitra"

@login_required
def katalog_page(request):
    form = ProductForm()
    return render(request, 'catalog/katalog.html', {
        'midtrans_client_key': settings.MIDTRANS_CLIENT_KEY,
        'is_admin': request.user.is_superuser,
        'is_mitra': is_mitra(request.user.userprofile.role),
        'form': form
    })

def get_products(request):
    search = request.GET.get('search', '')
    products = Product.objects.filter(name__icontains=search)
    is_user_mitra = is_mitra(request.user) if request.user.is_authenticated else False
    
    data = []
    for p in products:
        data.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            # Tentukan harga berdasarkan role
            "price": p.price_b2b if is_user_mitra else p.price_b2c,
            "stock": p.stock
        })
    return JsonResponse(data, safe=False)

@csrf_exempt
def add_product(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Hanya Admin yang dapat menambah produk.")
        
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            return JsonResponse({"status": "created"}, status=201)
        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

@csrf_exempt
def edit_product(request, id):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Hanya Admin yang dapat mengedit produk.")
        
    if request.method == 'POST':
        product = Product.objects.get(pk=id)
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            return JsonResponse({"status": "updated"})
        return JsonResponse({"status": "error", "errors": form.errors}, status=400)

@csrf_exempt
def calculate_shipping(request):
    if request.method == 'POST':
        body = json.loads(request.body)
        url = "https://api.rajaongkir.com/starter/cost"
        headers = {'key': settings.RAJAONGKIR_API_KEY, 'content-type': "application/x-www-form-urlencoded"}
        payload = f"origin=153&destination={body.get('destination')}&weight=1000&courier=jne"
        return JsonResponse(requests.post(url, data=payload, headers=headers).json())

@csrf_exempt
@login_required
def create_transaction(request):
    if request.method == 'POST':
        body = json.loads(request.body)
        product = Product.objects.get(pk=body.get('product_id'))
        shipping_cost = int(body.get('shipping_cost'))
        
        # Tentukan harga final berdasarkan role
        product_price = product.price_b2b if is_mitra(request.user) else product.price_b2c
        gross_amount = product_price + shipping_cost

        # Simpan pesanan ke database (Status: PENDING)
        order = Order.objects.create(
            user=request.user,
            product=product,
            total_amount=gross_amount
        )

        snap = midtransclient.Snap(is_production=False, server_key=settings.MIDTRANS_SERVER_KEY)
        param = {
            "transaction_details": {"order_id": order.order_id, "gross_amount": gross_amount},
            "item_details": [
                {"id": str(product.id), "price": product_price, "quantity": 1, "name": product.name},
                {"id": "SHIPPING", "price": shipping_cost, "quantity": 1, "name": "Ongkos Kirim"}
            ]
        }
        return JsonResponse({"token": snap.create_transaction(param)['token']})

@login_required
def get_orders(request):
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    data = [{"order_id": o.order_id, "product": o.product.name, "amount": o.total_amount, "status": o.get_status_display()} for o in orders]
    return JsonResponse(data, safe=False)