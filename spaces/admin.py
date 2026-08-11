from django.contrib import admin
from .models import Space, SpaceMember

admin.site.register(Space)
admin.site.register(SpaceMember)
# @admin.register(Space)
# class SpaceAdmin(admin.ModelAdmin):
#     pass

# @admin.register(SpaceMember)
