from django.contrib import admin
from .models import CustomUser
admin.site.register(CustomUser)
# @admin.register(CustomUser)
# class CustomUserAdmin(admin.ModelAdmin):
#     pass
