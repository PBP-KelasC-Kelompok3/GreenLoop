from django.urls import path
from . import views 

urlpatterns = [
    # Dashboard & Fitur Mitra B2B
    path('dashboard/', views.mitra_dashboard, name='mitra_dashboard'),
    path('pickup/create/', views.create_pickup, name='create_pickup'),
    path('pickup/<int:pickup_id>/edit/', views.edit_pickup, name='edit_pickup'),

    # Dashboard Admin & Update Status
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/update-status/<int:pickup_id>/<str:new_status>/', views.update_pickup_status, name='update_pickup_status'),
]