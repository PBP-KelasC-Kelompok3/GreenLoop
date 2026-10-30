import csv

from django.contrib import admin
from django.http import HttpResponse

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
    actions = ("export_profiles_csv",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user")

    @admin.action(description="Ekspor profil terpilih ke CSV")
    def export_profiles_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="mitra-profiles.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(("Nama Usaha", "Jenis Usaha", "PIC", "Telepon", "Username", "Email", "Provinsi", "Kota"))
        for profile in queryset.select_related("user").order_by("business_name"):
            writer.writerow((
                profile.business_name,
                profile.get_business_type_display(),
                profile.pic_name,
                profile.phone_number,
                profile.user.username,
                profile.user.email,
                profile.provinsi,
                profile.kota,
            ))
        return response
