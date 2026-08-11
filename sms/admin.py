from django.contrib import admin
from .models import SMSUsageLog
admin.site.register(SMSUsageLog)

# @admin.register(SMSUsageLog)
# class SMSUsageLogAdmin(admin.ModelAdmin):
#     pass