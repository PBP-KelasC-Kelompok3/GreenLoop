from django.urls import path
from . import views 

urlpatterns = [
    # Dashboard & Fitur Mitra B2B
    path('dashboard/', views.mitra_dashboard, name='mitra_dashboard'),
    path('pickup/create/', views.create_pickup, name='create_pickup'),
    path('pickup/<int:pickup_id>/edit/', views.edit_pickup, name='edit_pickup'),
    path('pickup/<int:pickup_id>/delete/', views.delete_pickup, name='delete_pickup'),
    path('pickup/history/', views.pickup_history, name='pickup_history'),

    # Dashboard Admin & Update Status
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    
    # 1. Untuk tombol link instan (Proses / Tolak) - Butuh 2 argumen (id & status)
    path('admin-panel/update-status/<int:pickup_id>/<str:new_status>/', views.update_pickup_status, name='update_pickup_status'),
    
    path('profile/', views.mitra_profile, name='mitra_profile'),
    path('profile/delete/', views.delete_mitra_profile, name='delete_mitra_profile'),
    path('profile/photo/', views.update_mitra_profile_photo, name='mitra_profile_photo'),
    
]
