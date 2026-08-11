from django.db import models


class ContactMessage(models.Model):
    """A public contact-form submission.

    This is intentionally public (AllowAny) — anyone, with or without an
    account, can reach out. No user FK is required; the submitter's details
    are captured directly on the record.
    """

    INQUIRY_TYPE_CHOICES = [
        ('general', 'General Inquiry'),
        ('sales', 'Sales & Wallet Billing'),
        ('sender_id', 'Custom Sender ID Purchase (v2)'),
        ('technical', 'Technical Support'),
    ]

    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    organization = models.CharField(max_length=255, blank=True)
    inquiry_type = models.CharField(
        max_length=20, choices=INQUIRY_TYPE_CHOICES, default='general'
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False, help_text='Whether support has reviewed this message')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.email}) - {self.get_inquiry_type_display()}"

