from django.contrib import admin

from .models import RewardTransaction, RewardVoucher, UserVoucher


@admin.register(RewardVoucher)
class RewardVoucherAdmin(admin.ModelAdmin):
    list_display = ('title', 'value_label', 'points_cost', 'is_active')
    list_filter = ('kind', 'is_active')
    search_fields = ('title', 'value_label', 'code')


@admin.register(RewardTransaction)
class RewardTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'kind', 'points_delta', 'balance_after', 'created_at')
    list_filter = ('kind', 'created_at')
    search_fields = ('user__username', 'description', 'source_reference')


@admin.register(UserVoucher)
class UserVoucherAdmin(admin.ModelAdmin):
    list_display = ('user', 'voucher', 'code', 'points_spent', 'expires_at', 'used_at')
    search_fields = ('user__username', 'code', 'voucher__title')
