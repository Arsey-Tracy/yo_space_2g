from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("account.urls")),
    path("api/billing/", include("subscriptions.urls")),
    path("api/", include("spaces.urls")),
    path("spaces/", include("spaces.urls")),  # Legacy webhook path compatibility
]
