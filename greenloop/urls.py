from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

# Import views utama
from .views import home, coming_soon, admin_dashboard

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('accounts/', include('accounts.urls')),
    path('scheduling/', include('scheduling.urls')),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('admin-dashboard/', admin_dashboard, name='admin_dashboard'),
    path('coming-soon/<slug:module>/', coming_soon, name='coming_soon'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)