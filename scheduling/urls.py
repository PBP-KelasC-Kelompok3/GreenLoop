from django.urls import path
from . import views 

urlpatterns = [
    # Dashboard & Fitur Mitra B2B
    path('dashboard/', views.mitra_dashboard, name='mitra_dashboard'),
    path('pickup/create/', views.create_pickup, name='create_pickup'),
    path('pickup/<int:pickup_id>/edit/', views.edit_pickup, name='edit_pickup'),
    path('pickup/history/', views.pickup_history, name='pickup_history'),

    # Dashboard Admin & Update Status
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    
    # 1. Untuk tombol link instan (Proses / Tolak) - Butuh 2 argumen (id & status)
    path('admin-panel/update-status/<int:pickup_id>/<str:new_status>/', views.update_pickup_status, name='update_pickup_status'),
    
    # 2. Untuk form modal Selesaikan - Hanya butuh 1 argumen (id saja)
    path('admin-panel/update-status/<int:pickup_id>/', views.update_pickup_status, name='update_pickup_status_form'),

    path('courier/dashboard/', views.courier_dashboard, name='courier_dashboard'),

    path('profile/', views.mitra_profile, name='mitra_profile'),
]