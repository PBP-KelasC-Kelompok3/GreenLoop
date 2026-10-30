from django.urls import path

from . import views


app_name = 'waste_reward'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('redeem/<int:voucher_id>/', views.redeem, name='redeem'),
    path('admin/vouchers/', views.manage_vouchers, name='admin_vouchers'),
    path('admin/vouchers/create/', views.create_voucher, name='create_voucher'),
    path('admin/vouchers/<int:voucher_id>/', views.manage_voucher_detail, name='manage_voucher_detail'),
    path('admin/vouchers/<int:voucher_id>/archive/', views.archive_voucher, name='archive_voucher'),
]
