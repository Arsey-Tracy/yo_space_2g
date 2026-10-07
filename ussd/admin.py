from django.contrib import admin

from .models import UssdSession, BroadcastSmsRecord


@admin.register(UssdSession)
class UssdSessionAdmin(admin.ModelAdmin):
    list_display = ("phone_number", "state", "space", "is_expired", "expires_at", "created_at")
    list_filter = ("state", "created_at")
    search_fields = ("phone_number",)
    readonly_fields = ("created_at", "updated_at", "expires_at")


@admin.register(BroadcastSmsRecord)
class BroadcastSmsRecordAdmin(admin.ModelAdmin):
    list_display = ("broadcast_id", "space", "recipient_count", "credits_deducted", "status", "created_at", "sent_at")
    list_filter = ("status", "created_at")
    search_fields = ("broadcast_id",)
    readonly_fields = ("created_at", "sent_at")
