from django.db import models
from account.models import Organization


class OrganizationSetting(models.Model):
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name='settings',
    )
    company_name = models.CharField(max_length=255, blank=True)
    default_language = models.CharField(max_length=20, default='en')
    sms_sender_id = models.CharField(max_length=20, blank=True)
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=True)
    voice_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'organization setting'
        verbose_name_plural = 'organization settings'

    def __str__(self):
        return f"Settings for {self.organization.name}"
