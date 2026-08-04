from django.db import models
from django.core.validators import MinValueValidator
from account.models import Organization


class Subscription(models.Model):
    NAME_CHOICES = [
        ('Standard', 'Standard'),
        ('Pro', 'Pro'),
        ('Premium', 'Premium'),
        ('Enterprise', 'Enterprise'),
    ]

    name = models.CharField(max_length=100, choices=NAME_CHOICES, unique=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], help_text="Monthly price in UGX")
    duration_in_days = models.PositiveIntegerField(default=30)
    max_spaces = models.PositiveIntegerField(default=1, help_text="Maximum allowed active spaces/groups")
    max_members_per_space = models.PositiveIntegerField(default=100, help_text="Maximum members per space")
    monthly_sms_quota = models.PositiveIntegerField(default=1000, help_text="Bulk SMS allowance per month")
    allow_merge_spaces = models.BooleanField(default=False)
    allow_public_private = models.BooleanField(default=False)
    allow_analytics = models.BooleanField(default=False)
    allow_reports = models.BooleanField(default=False)
    allow_surveys = models.BooleanField(default=False)
    features = models.TextField(help_text="Comma-separated list of features included in this plan", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - UGX {self.price:,.0f}/mo"

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"


class OrganizationSubscription(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='organization_subscriptions'
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name='organization_subscriptions'
    )
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.organization.name} - {self.subscription.name}"


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invoices')
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    invoice_number = models.CharField(max_length=50, unique=True)
    due_date = models.DateField()
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.organization.name} ({self.status})"


class SMSUsageLog(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='sms_logs')
    recipient_count = models.PositiveIntegerField()
    sms_cost_credits = models.PositiveIntegerField()
    description = models.CharField(max_length=255)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']

    def __str__(self):
        return f"{self.organization.name} used {self.sms_cost_credits} credits on {self.sent_at.strftime('%Y-%m-%d %H:%M')}"


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
    """
    Tracks each SMS credit top-up purchase made by an organization.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='sms_purchases')
    bundle = models.ForeignKey(SMSBundle, on_delete=models.SET_NULL, null=True, blank=True, related_name='purchases')
    sms_count = models.PositiveIntegerField(help_text="Number of SMS credits purchased")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=50, blank=True, help_text="e.g. Mobile Money, Bank Transfer")
    payment_reference = models.CharField(max_length=100, blank=True, help_text="External transaction ID")
    purchased_by = models.ForeignKey('account.CustomUser', on_delete=models.SET_NULL, null=True, blank=True)
    purchased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-purchased_at']

    def __str__(self):
        return f"{self.organization.name} bought {self.sms_count} SMS ({self.status})"
