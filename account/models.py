from django.db import models
from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    phone = models.CharField(max_length=20, blank=True, null=True)
    preferred_language = models.CharField(
        max_length=20,
        choices=[
            ('en', 'English'),
            ('lg', 'Luganda'),
            ('sw', 'Swahili'),
            ('rn', 'Runyakitara'),
            ('ach', 'Acholi')
        ],
        default='en'
    )

    def __str__(self):
        return self.username or self.email or self.phone or f"User #{self.id}"


class Organization(models.Model):
    owner = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='owned_organizations', null=True, blank=True)
    name = models.CharField(max_length=255)
    sender_id = models.CharField(max_length=11, blank=True, null=True, help_text="Custom SMS Sender ID")
    default_language = models.CharField(max_length=20, default='en')
    sms_balance = models.PositiveIntegerField(default=500, help_text="Remaining SMS credit balance")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def subscription_tier(self):
        return 'Pay-As-You-Go'

    def __str__(self):
        return self.name


class Member(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('communications', 'Communications Officer'),
        ('secretary', 'Secretary'),
        ('member', 'Member'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='org_memberships')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='members')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'organization')

    def __str__(self):
        return f"{self.user.username} - {self.role} - {self.organization.name}"
