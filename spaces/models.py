from django.db import models
from django.conf import settings
import random
import string


def generate_pin():
    """Generates a unique 4-digit PIN for USSD and Voice access."""
    return ''.join(random.choices(string.digits, k=4))


class Space(models.Model):
    """
    Core Space model representing community groups / spaces.
    Integrates organization ownership, USSD/Voice PIN access, and broadcast/survey communication.
    """
    organization = models.ForeignKey(
        'account.Organization',
        on_delete=models.CASCADE,
        related_name='spaces',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=100, help_text="Space name")
    description = models.TextField(blank=True)
    host_phone = models.CharField(max_length=20)
    pin = models.CharField(max_length=6, unique=True, default=generate_pin)
    is_public = models.BooleanField(default=True, help_text="Public spaces are visible in USSD browse")
    is_active = models.BooleanField(default=True, help_text="Is voice room live or active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Space '{self.name}' (PIN: {self.pin})"


class SpaceMember(models.Model):
    """
    Member belonging to a Space with specific permissions & contact phone number.
    """
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Administrator'
        COMMUNICATIONS = 'communications', 'Communications Officer'
        SECRETARY = 'secretary', 'Secretary'
        MEMBER = 'member', 'Member'

    space = models.ForeignKey(Space, related_name="members", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="space_memberships",
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    name = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("space", "phone_number")
        ordering = ['-joined_at']

    def __str__(self):
        return f"{self.name or self.phone_number} -> {self.space.name} ({self.role})"


class ActiveSpaceParticipant(models.Model):
    """
    Tracks participants currently connected to a live Voice conferencing room.
    """
    space = models.ForeignKey(Space, related_name="active_participants", on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20)
    call_session_id = models.CharField(max_length=100, blank=True, null=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("space", "phone_number")

    def masked_phone(self):
        if len(self.phone_number) >= 4:
            return f"****{self.phone_number[-4:]}"
        return self.phone_number


