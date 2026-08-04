from django.db import models
from spaces.models import Space
from django.conf import settings

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


