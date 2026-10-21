from django.contrib import admin

from .models import CourierProfile


@admin.register(CourierProfile)
class CourierProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "plate_number", "vehicle_type", "is_on_duty")
    list_filter = ("vehicle_type", "is_on_duty")
    search_fields = ("user__username", "user__email", "plate_number")