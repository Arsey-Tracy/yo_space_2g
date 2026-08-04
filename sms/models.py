from django.db import models
from spaces.models import Space
from django.conf import settings

# Create your models here.
class Broadcast(models.Model):
    """
    Bulk SMS broadcast sent or scheduled to all members of a Space.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    space = models.ForeignKey(Space, related_name='broadcasts', on_delete=models.CASCADE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_broadcasts',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    message = models.TextField()
    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft')
    recipients_count = models.PositiveIntegerField(default=0)
    cost_credits = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Broadcast to {self.space.name} ({self.status})"


from account.models import Organization

class SMSUsageLog(models.Model):
    """Simple log of SMS usage for an organization"""
    organization = models.ForeignKey(Organization, related_name='sms_usage_logs', on_delete=models.CASCADE)
    recipient_count = models.PositiveIntegerField(default=0)
    sms_cost_credits = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"SMSUsageLog for {self.organization.name} ({self.recipient_count} recipients)"
