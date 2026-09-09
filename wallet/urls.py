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
    SendSMSView,InitiateMarzpayPaymentView,
    MarzpayCallbackView,
    MarzpayPaymentStatusView,
)

router = DefaultRouter()
router.register(r'wallet', WalletViewSet, basename='wallet')
router.register(r'wallet/transactions', WalletTransactionViewSet, basename='wallettransaction')
router.register(r'wallet/usage', SmsUsageRecordViewSet, basename='smsusagerecord')
router.register(r'telecom-networks', TelecomNetworkViewSet, basename='telecomnetwork')

urlpatterns = [
    path('', include(router.urls)),
    
    # Wallet endpoints
    path('current/', WalletBalanceView.as_view(), name='wallet-current'),
    path('current', WalletBalanceView.as_view()),
    path('wallet/balance/', WalletBalanceView.as_view(), name='wallet-balance'),
    path('wallet/balance', WalletBalanceView.as_view()),
    
    # SMS bundles
    path('sms-bundles/', SMSBundleListView.as_view(), name='sms-bundle-list'),
    path('sms-bundles', SMSBundleListView.as_view()),
    # SMS purchase (ioTec payment)
    
    path('sms-bundles/purchase/', PurchaseSMSView.as_view(), name='sms-bundle-purchase'),
    path('sms-bundles/purchase', PurchaseSMSView.as_view()),
    path('sms-purchases/', SMSPurchaseHistoryView.as_view(), name='sms-purchase-history'),
    path('sms-purchases', SMSPurchaseHistoryView.as_view()),
    
    # ioTec payment flow
    # path('payments/status/<str:external_id>/', PaymentCollectionStatusView.as_view(), name='payment-collection-status'),
    # path('payments/status/<str:external_id>', PaymentCollectionStatusView.as_view()),
    # path('payments/callback/', PaymentCallbackView.as_view(), name='payment-callback'),
    # path('payments/callback', PaymentCallbackView.as_view()),
    
    # SMS sending
    path('sms/send/', SendSMSView.as_view(), name='send-sms'),
    path('sms/send', SendSMSView.as_view()),
    
    # MarzPay payment endpoints
    path('marzpay/initiate/', InitiateMarzpayPaymentView.as_view(), name='marzpay-initiate'),
    path('marzpay/initiate', InitiateMarzpayPaymentView.as_view()),
    path('marzpay/callback/', MarzpayCallbackView.as_view(), name='marzpay-callback'),
    path('marzpay/callback', MarzpayCallbackView.as_view()),
    path('marzpay/status/<str:reference>/', MarzpayPaymentStatusView.as_view(), name='marzpay-status'),
    path('marzpay/status/<str:reference>', MarzpayPaymentStatusView.as_view()),
]
