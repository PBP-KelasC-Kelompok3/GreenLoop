from django.urls import path
from . import views

app_name = "courier"

urlpatterns = [
    path("", views.show_dashboard, name="show_dashboard"),
]