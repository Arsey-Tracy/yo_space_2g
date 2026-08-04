from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    
    # Account & Auth
    path("api/auth/", include("account.urls")),
    path("auth/", include("account.urls")),
    
    # Subscriptions & Billing
    # path("api/billing/", include("subscriptions.urls")),
    # path("billing/", include("subscriptions.urls")),
    
    # Spaces App
    path("api/", include("spaces.urls")),
    
    # SMS App
    path("api/", include("sms.urls")),
    
    # Voice App
    path("api/", include("voice.urls")),
    
    # Survey App
    path("api/", include("survey.urls")),

    # Direct / Root Fallbacks
    path("", include("spaces.urls")),
    path('api/', include('wallet.urls')),
    path("", include("sms.urls")),
    path("", include("voice.urls")),
    path("", include("survey.urls")),
]
