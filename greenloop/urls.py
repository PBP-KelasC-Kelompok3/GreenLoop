from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

from .views import home, coming_soon, admin_dashboard

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('accounts/', include('accounts.urls')),
    path('courier/', include('courier.urls')),
    path('scheduling/', include('scheduling.urls')),
    path('mitra/waste-reward/', include('waste_reward.urls')),
    path('katalog/', include('catalog.urls')),

    # Placeholder sementara untuk modul teman.
    path(
        'coming-soon/<slug:module>/',
        coming_soon,
        name='coming_soon'
    ),
    path('admin-dashboard/', admin_dashboard, name='admin_dashboard'),
    path('coming-soon/<slug:module>/', coming_soon, name='coming_soon'),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )