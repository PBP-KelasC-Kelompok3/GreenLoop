from django.urls import path
from . import views

app_name = 'katalog'

urlpatterns = [
    path('katalog/', views.katalog_page, name='katalog_page'),
    path('katalog/api/products/', views.get_products, name='get_products'),
    path('katalog/api/products/add/', views.add_product, name='add_product'),
    path('katalog/api/products/edit/<int:id>/', views.edit_product, name='edit_product'),
    path('katalog/api/shipping/calculate/', views.calculate_shipping, name='calculate_shipping'),
    path('katalog/api/transaction/create/', views.create_transaction, name='create_transaction'),
    path('katalog/api/orders/', views.get_orders, name='get_orders'),
]