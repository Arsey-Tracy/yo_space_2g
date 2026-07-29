# pyrefly: ignore [missing-import]
from django.contrib import admin
# pyrefly: ignore [missing-import]
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # pyrefly: ignore [missing-import]
    path("api/auth/", include("account.urls")),
    path("auth/", include("account.urls")),
    # pyrefly: ignore [missing-import]
    path("api/billing/", include("subscriptions.urls")),
    path("billing/", include("subscriptions.urls")),
    # pyrefly: ignore [missing-import]
    path("api/", include("spaces.urls")),
    path("spaces/", include("spaces.urls")),
    path("", include("spaces.urls")),
]

