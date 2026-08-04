# pyrefly: ignore [missing-import]
from django.db import models
# pyrefly: ignore [missing-import]
from django.conf import settings
# from django.contrib.auth import get_user_model

# User = get_user_model()
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

