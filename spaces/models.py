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


class Survey(models.Model):
    """
    Survey / Poll conducted within a Space via Web or USSD.
    """
    space = models.ForeignKey(Space, related_name='surveys', on_delete=models.CASCADE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='created_surveys',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Survey: {self.title} ({self.space.name})"


class SurveyQuestion(models.Model):
    """
    Question within a Survey.
    """
    QUESTION_TYPES = [
        ('text', 'Text'),
        ('multiple_choice', 'Multiple Choice'),
        ('rating', 'Rating'),
    ]

    survey = models.ForeignKey(Survey, related_name='questions', on_delete=models.CASCADE)
    question_text = models.CharField(max_length=500)
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='multiple_choice')
    options = models.JSONField(default=list, blank=True, help_text="List of choices for multiple choice e.g. ['Yes', 'No']")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"Q: {self.question_text}"


class SurveyResponse(models.Model):
    """
    Responses submitted to a survey question.
    """
    survey_question = models.ForeignKey(SurveyQuestion, related_name='responses', on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='survey_responses',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    respondent_phone = models.CharField(max_length=20)
    answer_text = models.TextField(blank=True)
    answer_value = models.CharField(max_length=100, blank=True)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-answered_at']

    def __str__(self):
        return f"{self.respondent_phone} -> {self.survey_question.question_text[:30]}"
