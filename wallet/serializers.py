# pyrefly: ignore [missing-import]
from rest_framework import serializers
# pyrefly: ignore [missing-import]
from .models import Wallet, WalletTransaction, SmsUsageRecord

class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ['id', 'organization', 'balance_credits', 'cash_balance_ugx', 'updated_at']
        read_only_fields = ['id', 'balance_credits', 'cash_balance_ugx', 'updated_at']

class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ['id', 'wallet', 'transaction_type', 'amount_paid_ugx', 'credits_added',
                  'payment_method', 'payment_reference', 'initiated_by', 'created_at', 'notes']
        read_only_fields = ['id', 'credits_added', 'created_at']

class SmsUsageRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SmsUsageRecord
        fields = ['id', 'wallet', 'broadcast_id', 'recipients_count', 'credits_deducted',
                  'status', 'created_at']
        read_only_fields = ['id', 'credits_deducted', 'created_at']

class TelecomNetworkSerializer(serializers.ModelSerializer):
    class Meta:
        from .models import TelecomNetwork
        model = TelecomNetwork
        fields = ['id', 'name', 'code', 'provider_cost_ugx', 'markup_ugx', 'selling_price_ugx', 'is_active', 'updated_at']

