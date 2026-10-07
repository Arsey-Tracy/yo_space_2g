from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


USSD_SESSION_TTL_MINUTES = getattr(settings, "USSD_SESSION_TTL_MINUTES", 10)


def default_session_expires_at():
    return timezone.now() + timedelta(minutes=USSD_SESSION_TTL_MINUTES)


class ActiveUssdSessionManager(models.Manager):
    """Manager that scopes queries to non-expired sessions."""

    def active(self):
        return self.filter(expires_at__gt=timezone.now())

    def cleanup_expired(self):
        """Delete all sessions whose expires_at has passed. Returns count deleted."""
        return self.filter(expires_at__lte=timezone.now()).delete()


class UssdSession(models.Model):
    """Persistent USSD session stored in the database for reliability across
    process restarts and multiple workers.

    Only IDs and small state identifiers are stored in ``data`` — never PINs,
    passwords, or other secrets.
    """

    phone_number = models.CharField(max_length=20, db_index=True)
    state = models.CharField(max_length=50, default="main_menu")
    space = models.ForeignKey(
        "spaces.Space",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ussd_sessions",
    )
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(
        default=default_session_expires_at,
        help_text="Sessions expire after %d minutes of inactivity"
        % USSD_SESSION_TTL_MINUTES,
    )

    objects = ActiveUssdSessionManager()

    class Meta:
        db_table = "ussd_sessions"
        indexes = [
            models.Index(fields=["phone_number"]),
            models.Index(fields=["state"]),
            models.Index(fields=["expires_at"]),
        ]

    def is_expired(self):
        return self.expires_at <= timezone.now()

    def extend(self):
        """Push expires_at forward to keep the session alive."""
        self.expires_at = default_session_expires_at()
        self.save(update_fields=["expires_at"])

    def reset(self):
        """Return the session to its initial state and refresh its expiry."""
        self.state = "main_menu"
        self.space = None
        self.data = {}
        self.expires_at = default_session_expires_at()
        self.save(update_fields=["state", "space", "data", "expires_at"])

    def refresh_data(self, **kwargs):
        """Merge ``kwargs`` into the ``data`` dict and persist."""
        current = dict(self.data or {})
        current.update(kwargs)
        self.data = current
        self.save(update_fields=["data"])

    def __str__(self):
        return f"USSD Session {self.phone_number}: {self.state}"


class BroadcastSmsRecord(models.Model):
    """Record of an SMS broadcast originating from a USSD session, linked
    to the wallet usage record so credits can be refunded on failure.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("refunded", "Refunded"),
        ("failed", "Failed"),
    ]

    broadcast_id = models.CharField(max_length=100, unique=True)
    usage_record = models.ForeignKey(
        "wallet.SmsUsageRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ussd_broadcast_records",
    )
    space = models.ForeignKey(
        "spaces.Space",
        on_delete=models.CASCADE,
        related_name="ussd_broadcast_records",
    )
    recipient_count = models.IntegerField()
    credits_deducted = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "broadcast_sms_records"

    def __str__(self):
        return f"Broadcast {self.broadcast_id}: {self.recipient_count} recipients"
