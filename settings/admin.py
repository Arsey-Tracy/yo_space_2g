from django.contrib import admin

from .models import OrganizationSetting


@admin.register(OrganizationSetting)
class OrganizationSettingAdmin(admin.ModelAdmin):
    list_display = ('organization', 'default_language', 'sms_sender_id', 'email_notifications', 'sms_notifications', 'voice_enabled')
    list_filter = ('default_language', 'email_notifications', 'sms_notifications', 'voice_enabled')
    search_fields = ('organization__name', 'sms_sender_id')
