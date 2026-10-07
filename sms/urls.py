from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import BroadcastViewSet, sms_delivery_report

router = DefaultRouter()
router.register("broadcasts", BroadcastViewSet, basename="broadcast")

urlpatterns = [
    path("sms/dlr/", sms_delivery_report, name="sms-delivery-report"),
    path("dlr/", sms_delivery_report, name="sms-delivery-report-short"),
    path("sms/", include(router.urls)),
]
