from django.core.validators import MinValueValidator
from django.db import models
from django.conf import settings

from account.models import Organization

User = settings.AUTH_USER_MODEL

class Wallet(models.Model):
    """Prepaid wallet for an organization.

    Each organization has exactly one wallet (OneToOne). The wallet tracks the number of SMS credits
    available (`balance_credits`) and any residual cash that is insufficient for another credit
    (`cash_balance_ugx`).
    """
    organization = models.OneToOneField('account.Organization', on_delete=models.CASCADE, related_name='wallet')
    balance_credits = models.PositiveIntegerField(default=0, help_text='Number of SMS credits available')
    cash_balance_ugx = models.PositiveIntegerField(default=0, help_text='Remaining UGX cash that is insufficient for another credit')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet for {self.organization.name} – {self.balance_credits} credits"

class WalletTransaction(models.Model):
    """Log of top‑up and deduction actions performed on a wallet."""
    TRANSACTION_TYPE_CHOICES = [
        ('topup', 'Top‑up'),
        ('deduction', 'Deduction'),
    ]
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    amount_paid_ugx = models.PositiveIntegerField(help_text='UGX amount paid by the organization')
    credits_added = models.IntegerField(help_text='SMS credits added (positive) or deducted (negative)')
    payment_method = models.CharField(max_length=50, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    initiated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.get_transaction_type_display()} – {self.credits_added} credits on {self.created_at:%Y-%m-%d}" 

class SmsUsageRecord(models.Model):
    """Record of an SMS broadcast and the credits it consumed."""
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='usage_records')
    broadcast_id = models.CharField(max_length=100, unique=True)
    recipients_count = models.PositiveIntegerField()
    credits_deducted = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default='sent')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Broadcast {self.broadcast_id} – {self.credits_deducted} credits"


class TelecomNetwork(models.Model):
    """Configurable Pay-As-You-Go pricing rules per telecom operator."""
    name = models.CharField(max_length=100, unique=True, help_text="e.g. MTN Uganda, Airtel Uganda")
    code = models.CharField(max_length=20, unique=True, help_text="e.g. MTN, AIRTEL, OTHER")
    provider_cost_ugx = models.PositiveIntegerField(help_text="Cost charged by Africa's Talking (e.g., MTN: 27, Airtel: 25, Other: 35)")
    markup_ugx = models.PositiveIntegerField(help_text="Fixed markup amount in UGX (e.g., MTN: 13, Airtel: 15, Other: 15)")
    selling_price_ugx = models.PositiveIntegerField(help_text="Selling price charged to customer in UGX (provider_cost_ugx + markup_ugx)")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        # Enforce selling_price = provider_cost + markup if not explicitly overriden
        if not self.selling_price_ugx:
            self.selling_price_ugx = self.provider_cost_ugx + self.markup_ugx
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code}) - Base: {self.provider_cost_ugx} UGX, Selling: {self.selling_price_ugx} UGX"

class SMSBundle(models.Model):
    """
    Pre-defined SMS credit bundles available for purchase.
    Organizations buy these when their initial tier credits run low.
    """
    name = models.CharField(max_length=100, help_text="Bundle display name e.g. 'Starter Pack'")
    sms_count = models.PositiveIntegerField(help_text="Number of SMS credits in this bundle")
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], help_text="Price in UGX")
    price_per_sms = models.DecimalField(max_digits=8, decimal_places=2, default=0, help_text="Calculated cost per single SMS")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['price']

    def save(self, *args, **kwargs):
        if self.sms_count > 0:
            self.price_per_sms = self.price / self.sms_count
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.sms_count} SMS @ UGX {self.price:,.0f}"


class SMSPurchase(models.Model):
    """Record of SMS credits purchased via payment."""
    PAYMENT_METHOD_CHOICES = [
        ('mobile_money', 'Mobile Money'),
        ('pesapal', 'PesaPal'),
        ('iotec', 'ioTec'),
        ('card', 'Card'),
        ('marzpay', 'Marzpay'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    organization = models.ForeignKey('account.Organization', on_delete=models.CASCADE, related_name='sms_purchases')
    bundle = models.ForeignKey(SMSBundle, on_delete=models.SET_NULL, null=True, blank=True)
    sms_count = models.PositiveIntegerField()
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='pesapal')
    payment_reference = models.CharField(max_length=100, unique=True)
    pesapal_tracking_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    pesapal_order_id = models.CharField(max_length=100, blank=True)
    purchased_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    purchased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-purchased_at']
        indexes = [
            models.Index(fields=['organization', '-purchased_at']),
            models.Index(fields=['payment_reference']),
            models.Index(fields=['pesapal_tracking_id']),
        ]

    def __str__(self):
        return f"SMS Purchase - {self.sms_count} SMS for {self.organization.name} ({self.status})"

class MarzpayPayment(models.Model):
    """Track MarzPay Mobile Money collection transactions."""
    STATUS_CHOICES = [
        ('initiated', 'Initiated'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    organization = models.ForeignKey('account.Organization', on_delete=models.CASCADE, related_name='marzpay_payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='UGX')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='initiated')

    # MarzPay identifiers
    reference = models.CharField(max_length=100, unique=True, help_text="UUID v4 sent as request reference")
    transaction_uuid = models.CharField(max_length=100, blank=True, null=True, unique=True, help_text="MarzPay system UUID")
    provider_transaction_id = models.CharField(max_length=100, blank=True, null=True, help_text="Telco network ID (e.g. MTN/Airtel ID)")

    sms_purchase = models.OneToOneField(SMSPurchase, on_delete=models.SET_NULL, null=True, blank=True, related_name='marzpay_payment')

    customer_phone = models.CharField(max_length=20)
    description = models.TextField(blank=True)

    initiated_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_updated_at = models.DateTimeField(auto_now=True)
    webhook_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-initiated_at']
        indexes = [
            models.Index(fields=['organization', '-initiated_at']),
            models.Index(fields=['reference']),
            models.Index(fields=['transaction_uuid']),
        ]

    def __str__(self):
        return f"MarzPay Payment - UGX {self.amount} ({self.status})"