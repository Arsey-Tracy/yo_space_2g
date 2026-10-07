from django.contrib import admin

from .models import Broadcast, SMSUsageLog


@admin.register(Broadcast, SMSUsageLog)
class SmsAdmin(admin.ModelAdmin):
	"""Register SMS records with Django's default administration views."""