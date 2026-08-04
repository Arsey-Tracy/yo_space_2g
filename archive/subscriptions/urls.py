from django.urls import path
from .views import (
    SubscriptionListView, CurrentSubscriptionView, UpgradeSubscriptionView,
    InvoiceListView, SMSBundleListView, PurchaseSMSView,
    SMSPurchaseHistoryView, SMSBalanceView, TestPaymentView, VerifyPaymentView
)

urlpatterns = [
    path('plans/', SubscriptionListView.as_view(), name='subscription-plans'),
    path('plans', SubscriptionListView.as_view()),
    path('current/', CurrentSubscriptionView.as_view(), name='subscription-current'),
    path('current', CurrentSubscriptionView.as_view()),
    path('subscribe/', UpgradeSubscriptionView.as_view(), name='subscription-upgrade'),
    path('subscribe', UpgradeSubscriptionView.as_view()),
    path('invoices/', InvoiceListView.as_view(), name='subscription-invoices'),
    path('invoices', InvoiceListView.as_view()),

    # SMS Bundle Purchase (Top-Up / Pay-As-You-Go)
    path('sms-bundles/', SMSBundleListView.as_view(), name='sms-bundles'),
    path('sms-bundles', SMSBundleListView.as_view()),
    path('sms-bundles/purchase/', PurchaseSMSView.as_view(), name='sms-purchase'),
    path('sms-bundles/purchase', PurchaseSMSView.as_view()),
    path('sms-bundles/history/', SMSPurchaseHistoryView.as_view(), name='sms-purchase-history'),
    path('sms-bundles/history', SMSPurchaseHistoryView.as_view()),
    path('sms-balance/', SMSBalanceView.as_view(), name='sms-balance'),
    path('sms-balance', SMSBalanceView.as_view()),
    path('test-payment/', TestPaymentView.as_view(), name='test-payment'),
    path('test-payment', TestPaymentView.as_view()),
    path('verify-payment/', VerifyPaymentView.as_view(), name='verify-payment'),
    path('verify-payment', VerifyPaymentView.as_view()),
]
