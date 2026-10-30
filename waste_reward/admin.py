from django.contrib import admin
from django.db.models import Count

from .models import RewardTransaction, RewardVoucher, UserVoucher


@admin.register(RewardVoucher)
class RewardVoucherAdmin(admin.ModelAdmin):
    actions = ('activate_vouchers', 'deactivate_vouchers')
    list_display = (
        'title', 'kind', 'value_label', 'points_cost', 'valid_days',
        'redemption_count', 'is_active',
    )
    list_filter = ('kind', 'is_active')
    search_fields = ('title', 'value_label', 'code', 'description')
    ordering = ('sort_order', 'points_cost')
    list_per_page = 50
    readonly_fields = ('redemption_count',)

    @admin.display(description='Penukaran', ordering='redemption_count')
    def redemption_count(self, obj):
        return obj.redemption_count

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            redemption_count=Count('redemptions')
        )

    @admin.action(description='Aktifkan voucher terpilih')
    def activate_vouchers(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} voucher diaktifkan.')

    @admin.action(description='Nonaktifkan voucher terpilih (arsipkan)')
    def deactivate_vouchers(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} voucher diarsipkan.')

    def has_delete_permission(self, request, obj=None):
        # Voucher yang pernah digunakan disimpan agar relasi historis tetap utuh.
        return False


@admin.register(RewardTransaction)
class RewardTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'kind', 'points_delta', 'balance_after', 'created_at')
    list_filter = ('kind', 'created_at')
    search_fields = ('user__username', 'description', 'source_reference')
    list_select_related = ('user',)
    date_hierarchy = 'created_at'
    list_per_page = 50
    readonly_fields = tuple(field.name for field in RewardTransaction._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserVoucher)
class UserVoucherAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'voucher', 'code', 'points_spent', 'expires_at',
        'used_at', 'used_order_reference',
    )
    list_filter = ('used_at', 'expires_at')
    search_fields = (
        'user__username', 'code', 'voucher__title', 'used_order_reference',
    )
    list_select_related = ('user', 'voucher')
    date_hierarchy = 'acquired_at'
    list_per_page = 50
    readonly_fields = tuple(field.name for field in UserVoucher._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
