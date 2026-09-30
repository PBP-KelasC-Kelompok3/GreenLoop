from django.contrib import admin
from django.urls import include, path

from .views import home, coming_soon


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('accounts/', include('accounts.urls')),

    # Placeholder sementara untuk modul teman.
    path(
        'coming-soon/<slug:module>/',
        coming_soon,
        name='coming_soon'
    ),
]