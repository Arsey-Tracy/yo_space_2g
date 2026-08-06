# pyrefly: ignore [missing-import]
from django.urls import path, include
# pyrefly: ignore [missing-import]
from rest_framework.routers import DefaultRouter
# pyrefly: ignore [missing-import]
from .views import (
    WalletViewSet,
    WalletTransactionViewSet,
    SmsUsageRecordViewSet,
    TelecomNetworkViewSet,
    WalletBalanceView,
    SMSBundleListView,
    PurchaseSMSView,
    SMSPurchaseHistoryView,
)

router = DefaultRouter()
router.register(r'wallet', WalletViewSet, basename='wallet')
router.register(r'wallet/transactions', WalletTransactionViewSet, basename='wallettransaction')
router.register(r'wallet/usage', SmsUsageRecordViewSet, basename='smsusagerecord')
router.register(r'telecom-networks', TelecomNetworkViewSet, basename='telecomnetwork')

urlpatterns = [
    path('', include(router.urls)),
    path('current/', WalletBalanceView.as_view(), name='wallet-current'),
    path('current', WalletBalanceView.as_view()),
    path('wallet/balance/', WalletBalanceView.as_view(), name='wallet-balance'),
    path('sms-bundles/', SMSBundleListView.as_view(), name='sms-bundle-list'),
    path('sms-bundles/purchase/', PurchaseSMSView.as_view(), name='sms-bundle-purchase'),
    path('sms-purchases/', SMSPurchaseHistoryView.as_view(), name='sms-purchase-history'),
]

