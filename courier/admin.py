from django.contrib import admin

from .models import CourierProfile, WeightLog


# Mendaftarkan profil kurir ke halaman /admin lengkap dengan kolom, filter, dan pencarian
@admin.register(CourierProfile)
class CourierProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "plate_number", "vehicle_type", "is_on_duty")
    list_filter = ("vehicle_type", "is_on_duty")
    search_fields = ("user__username", "user__email", "plate_number")
 
 
# Mendaftarkan catatan timbangan ke halaman /admin
@admin.register(WeightLog)
class WeightLogAdmin(admin.ModelAdmin):
    list_display = ("collected_at", "courier", "partner_name", "weight_kg")
    list_filter = ("collected_at", "courier")
    search_fields = ("partner_name", "courier__username")
 