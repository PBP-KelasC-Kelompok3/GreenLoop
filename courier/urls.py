from django.urls import path
from . import route_views, views

app_name = "courier"

urlpatterns = [
    path("", views.show_dashboard, name="show_dashboard"),
    path("route/", route_views.show_route_today, name="show_route_today"),
    path("route/data/", route_views.route_data, name="route_data"),
    path("route/<int:pk>/start/", route_views.start_pickup, name="start_pickup"),
    path("route/<int:pk>/finish/", route_views.finish_pickup, name="finish_pickup"),
    path("duty/", route_views.toggle_duty, name="toggle_duty"),
    path("history/", views.show_history, name="show_history"),
    path("recap/", views.show_recap, name="show_recap"),
    path("recap/list/", views.recap_list, name="recap_list"),
    path("recap/create/", views.create_weight_log, name="create_weight_log"),
    path("recap/<int:pk>/update/", views.update_weight_log, name="update_weight_log"),
    path("recap/<int:pk>/delete/", views.delete_weight_log, name="delete_weight_log"),
    path("profile/", views.show_profile, name="show_profile"),
    path("profile/edit/", views.update_profile, name="update_profile"),
    path("profile/password/", views.change_password, name="change_password"),
]