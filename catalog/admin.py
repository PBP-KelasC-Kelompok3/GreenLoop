from django.contrib import admin

from .models import Order, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_b2c', 'price_b2b', 'stock', 'weight_grams')
    search_fields = ('name', 'description')
    list_editable = ('price_b2c', 'price_b2b', 'stock')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'user', 'product_name', 'quantity', 'total_amount', 'status', 'created_at')
    list_filter = ('status', 'created_at', 'courier_code')
    search_fields = ('order_id', 'user__username', 'recipient_name', 'phone')
    readonly_fields = (
        'order_id', 'user', 'product', 'product_name', 'quantity', 'unit_price',
        'subtotal', 'shipping_cost', 'goods_discount', 'shipping_discount',
        'voucher', 'total_amount', 'created_at', 'payment_token',
    )
