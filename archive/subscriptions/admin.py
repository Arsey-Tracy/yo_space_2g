from django.contrib import admin
from .models import Subscription, OrganizationSubscription

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'duration_in_days', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)

@admin.register(OrganizationSubscription)
class OrganizationSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('organization', 'subscription', 'start_date', 'end_date', 'is_active')
    list_filter = ('is_active', 'start_date', 'end_date')
    search_fields = ('organization__name', 'subscription__name')
