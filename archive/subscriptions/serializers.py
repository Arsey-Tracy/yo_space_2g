from rest_framework import serializers
from .models import Subscription, OrganizationSubscription, Invoice, SMSUsageLog, SMSBundle, SMSPurchase


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = [
            'id', 'name', 'price', 'duration_in_days',
            'max_spaces', 'max_members_per_space', 'monthly_sms_quota',
            'allow_merge_spaces', 'allow_public_private',
            'allow_analytics', 'allow_reports', 'allow_surveys',
            'features', 'is_active'
        ]


class OrganizationSubscriptionSerializer(serializers.ModelSerializer):
    subscription_details = SubscriptionSerializer(source='subscription', read_only=True)

    class Meta:
        model = OrganizationSubscription
        fields = ['id', 'organization', 'subscription', 'subscription_details', 'start_date', 'end_date', 'is_active']


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ['id', 'organization', 'subscription', 'amount', 'status', 'invoice_number', 'due_date', 'paid_at', 'created_at']


class SMSUsageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSUsageLog
        fields = ['id', 'organization', 'recipient_count', 'sms_cost_credits', 'description', 'sent_at']


class SMSBundleSerializer(serializers.ModelSerializer):
    class Meta:
        model = SMSBundle
        fields = ['id', 'name', 'sms_count', 'price', 'price_per_sms', 'is_active']


class SMSPurchaseSerializer(serializers.ModelSerializer):
    bundle_name = serializers.CharField(source='bundle.name', read_only=True, default='Custom')

    class Meta:
        model = SMSPurchase
        fields = [
            'id', 'organization', 'bundle', 'bundle_name', 'sms_count',
            'amount_paid', 'status', 'payment_method', 'payment_reference',
            'purchased_by', 'purchased_at'
        ]
        read_only_fields = ['id', 'organization', 'sms_count', 'amount_paid', 'status', 'purchased_by', 'purchased_at']


class PurchaseSMSSerializer(serializers.Serializer):
    """Request serializer for buying an SMS bundle."""
    bundle_id = serializers.IntegerField()
    payment_method = serializers.CharField(max_length=50, required=False, default='Mobile Money')
    payment_reference = serializers.CharField(max_length=100, required=False, default='')
