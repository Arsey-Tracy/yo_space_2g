from django.urls import path

from .views import OrganizationSettingsView

urlpatterns = [
    path('', OrganizationSettingsView.as_view(), name='organization-settings'),
]
