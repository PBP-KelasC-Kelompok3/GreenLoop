from django.urls import path

from . import views

app_name = 'katalog'

urlpatterns = [
    path('', views.katalog_page, name='katalog_page'),
    path('preview/', views.catalog_preview, name='catalog_preview'),
    path('preview/produk/<int:product_id>/', views.product_detail_preview, name='product_detail_preview'),
    path('produk/<int:product_id>/', views.product_detail, name='product_detail'),
    path('admin/produk/', views.admin_products_page, name='admin_products'),
    path('admin/produk/add/', views.add_admin_product, name='add_admin_product'),
    path('admin/produk/<int:product_id>/update/', views.update_admin_product, name='update_admin_product'),
    path('admin/produk/<int:product_id>/delete/', views.delete_admin_product, name='delete_admin_product'),
    path('keranjang/', views.cart_page, name='cart'),
    path('checkout/', views.checkout_page, name='checkout'),
    path('pesanan/', views.orders_page, name='orders'),
    path('admin/pesanan/', views.admin_orders_page, name='admin_orders'),
    path('admin/pesanan/<str:order_id>/update/', views.update_admin_order, name='update_admin_order'),
    path('pesanan/<str:order_id>/', views.order_tracking, name='order_tracking'),
    path('api/products/', views.get_products, name='get_products'),
    path('api/products/add/', views.add_product, name='add_product'),
    path('api/products/edit/<int:id>/', views.edit_product, name='edit_product'),
    path('api/cart/add/', views.add_to_cart, name='add_to_cart'),
    path('api/cart/<int:product_id>/', views.update_cart_item, name='update_cart_item'),
    path('api/shipping/destinations/', views.search_destinations_api, name='search_destinations'),
    path('api/shipping/calculate/', views.calculate_shipping_api, name='calculate_shipping'),
    path('api/orders/create/', views.create_order, name='create_order'),
    path('api/orders/', views.get_orders, name='get_orders'),
    path('api/orders/<str:order_id>/refresh-payment/', views.refresh_order_payment, name='refresh_order_payment'),
    path('api/payment/notification/', views.midtrans_notification, name='midtrans_notification'),
]
