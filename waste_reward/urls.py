from django.urls import path

from . import views


app_name = 'waste_reward'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('redeem/<int:voucher_id>/', views.redeem, name='redeem'),
]
