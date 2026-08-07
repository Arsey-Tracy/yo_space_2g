from rest_framework import serializers
from .models import (
    Wallet,
    WalletTransaction,
    SmsUsageRecord,
    TelecomNetwork,
    SMSBundle,
    SMSPurchase,
)


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['id', 'organization', 'balance_credits', 'cash_balance_ugx', 'updated_at']
        read_only_fields = ['id', 'balance_credits', 'cash_balance_ugx', 'updated_at']


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = [
            'id', 'wallet', 'transaction_type', 'amount_paid_ugx', 'credits_added',
            'payment_method', 'payment_reference', 'initiated_by', 'created_at', 'notes'
        ]
        read_only_fields = ['id', 'credits_added', 'created_at']


class SmsUsageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsUsageRecord
        fields = [
            'id', 'wallet', 'broadcast_id', 'recipients_count', 'credits_deducted',
            'status', 'created_at'
        ]
        read_only_fields = ['id', 'credits_deducted', 'created_at']


class TelecomNetworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelecomNetwork
        fields = [
            'id', 'name', 'code', 'provider_cost_ugx', 'markup_ugx', 'selling_price_ugx', 'is_active', 'updated_at'
        ]


class SMSBundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSBundle
        fields = ['id', 'name', 'sms_count', 'price', 'price_per_sms', 'is_active']


class SMSPurchaseSerializer(serializers.ModelSerializer):
    bundle_name = serializers.CharField(source='bundle.name', read_only=True, default='Custom')

    class Meta:
        model = SMSPurchase
        fields = [
            'id', 'organization', 'bundle', 'bundle_name', 'sms_count', 'amount_paid',
            'status', 'payment_method', 'payment_reference', 'purchased_by', 'purchased_at'
        ]
        read_only_fields = [
            'id', 'sms_count', 'amount_paid', 'status', 'payment_method',
            'payment_reference', 'purchased_by', 'purchased_at', 'bundle_name'
        ]


class PurchaseSMSSerializer(serializers.Serializer):
    bundle_id = serializers.IntegerField(required=False)
    custom_amount = serializers.DecimalField(required=False, max_digits=10, decimal_places=2, min_value=0)
    payment_method = serializers.CharField(max_length=50, default='Mobile Money')
    payment_reference = serializers.CharField(max_length=100, allow_blank=True, required=False)
    phone_number = serializers.CharField(max_length=20, allow_blank=True, required=False)
    external_id = serializers.CharField(max_length=100, allow_blank=True, required=False)

