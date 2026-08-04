# pyrefly: ignore [missing-import]
from django.urls import path, include
# pyrefly: ignore [missing-import]
from rest_framework.routers import DefaultRouter
# pyrefly: ignore [missing-import]
from .views import WalletViewSet, WalletTransactionViewSet, SmsUsageRecordViewSet, TelecomNetworkViewSet

router = DefaultRouter()
router.register(r'wallet', WalletViewSet, basename='wallet')
router.register(r'wallet/transactions', WalletTransactionViewSet, basename='wallettransaction')
router.register(r'wallet/usage', SmsUsageRecordViewSet, basename='smsusagerecord')
router.register(r'telecom-networks', TelecomNetworkViewSet, basename='telecomnetwork')

urlpatterns = [
    path('', include(router.urls)),
]

