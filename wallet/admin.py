# pyrefly: ignore [missing-import]
from django.contrib import admin
# pyrefly: ignore [missing-import]
from .models import Wallet, WalletTransaction, SmsUsageRecord, TelecomNetwork

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('organization', 'balance_credits', 'cash_balance_ugx', 'updated_at')
    readonly_fields = ('balance_credits', 'cash_balance_ugx', 'updated_at')
    search_fields = ('organization__name',)

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'transaction_type', 'amount_paid_ugx', 'credits_added', 'created_at')
    readonly_fields = ('created_at',)
    list_filter = ('transaction_type',)
    search_fields = ('wallet__organization__name', 'payment_reference')

@admin.register(SmsUsageRecord)
class SmsUsageRecordAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'broadcast_id', 'recipients_count', 'credits_deducted', 'status', 'created_at')
    readonly_fields = ('created_at',)
    list_filter = ('status',)
    search_fields = ('broadcast_id', 'wallet__organization__name')

@admin.register(TelecomNetwork)
class TelecomNetworkAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'provider_cost_ugx', 'markup_ugx', 'selling_price_ugx', 'is_active', 'updated_at')
    list_editable = ('provider_cost_ugx', 'markup_ugx', 'selling_price_ugx', 'is_active')
    search_fields = ('name', 'code')

