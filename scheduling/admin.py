from django.contrib import admin

from .models import MitraProfile


@admin.register(MitraProfile)
class MitraProfileAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "business_type",
        "pic_name",
        "phone_number",
        "user",
        "kota",
    )
    list_filter = ("business_type", "provinsi", "kota")
    search_fields = (
        "business_name",
        "pic_name",
        "phone_number",
        "user__username",
        "user__email",
    )
    readonly_fields = ("created_at",)
