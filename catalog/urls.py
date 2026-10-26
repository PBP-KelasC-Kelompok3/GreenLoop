from django.urls import path
from . import views

app_name = 'katalog'

urlpatterns = [
    path('', views.katalog_page, name='katalog_page'),
    path('api/products/', views.get_products, name='get_products'),
    path('api/products/add/', views.add_product, name='add_product'),
    path('api/products/edit/<int:id>/', views.edit_product, name='edit_product'),
    path('api/shipping/calculate/', views.calculate_shipping, name='calculate_shipping'),
    path('api/transaction/create/', views.create_transaction, name='create_transaction'),
    path('api/orders/', views.get_orders, name='get_orders'),
]