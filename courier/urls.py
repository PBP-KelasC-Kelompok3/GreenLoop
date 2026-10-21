from django.urls import path
from . import views

app_name = "courier"

urlpatterns = [
    path("", views.show_dashboard, name="show_dashboard"),
    path("route/", views.show_route_today, name="show_route_today"),
    path("history/", views.show_history, name="show_history"),
    path("recap/", views.show_recap, name="show_recap"),
    path("profile/", views.show_profile, name="show_profile"),
    path("profile/edit/", views.update_profile, name="update_profile"),
    path("profile/password/", views.change_password, name="change_password"),
]