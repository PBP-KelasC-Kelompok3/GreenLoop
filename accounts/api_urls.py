from django.urls import path

from .api_views import (
    CsrfTokenAPIView,
    LoginAPIView,
    LogoutAPIView,
    ReadProfileAPIView,
    RegisterAPIView,
)


app_name = 'accounts_api'

urlpatterns = [
    path('csrf/', CsrfTokenAPIView.as_view(), name='csrf'),
    path('register/', RegisterAPIView.as_view(), name='register'),
    path('login/', LoginAPIView.as_view(), name='login'),
    path('logout/', LogoutAPIView.as_view(), name='logout'),
    path('profile/', ReadProfileAPIView.as_view(), name='profile'),
]
