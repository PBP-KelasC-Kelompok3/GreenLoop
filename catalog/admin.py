from django.contrib import admin

from .models import Order, OrderItem, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price_b2c', 'price_b2b', 'stock', 'weight_grams')
    search_fields = ('name',)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product_name', 'unit_price', 'quantity')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'user', 'total_amount', 'payment_status', 'status', 'tracking_number', 'created_at')
    list_filter = ('payment_status', 'status', 'created_at')
    search_fields = ('order_id', 'user__username', 'tracking_number')
    list_editable = ('status', 'tracking_number')
    readonly_fields = ('order_id', 'user', 'subtotal', 'shipping_cost', 'total_amount', 'goods_discount', 'shipping_discount', 'created_at')
    inlines = (OrderItemInline,)