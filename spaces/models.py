from django.db import models
import random, string
# Create your models here.

def generate_pin():
    """A method for generating 4 Digit space pins for access"""
    return ''.join(random.choices(string.digits, k=4))

class Space(models.Model):
    name = models.CharField(max_length=100, help_text="space name")
    host_phone = models.CharField()
    pin = models.CharField(max_length=4, unique=True, default=generate_pin)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ("name", "host_phone")
    
    def __str__(self):
        return f"YoSpace{self.name} is created and you PIN is ({self.pin})"

class SpaceInvitee(models.Model):
    space = models.ForeignKey(Space, related_name="invitees", on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=15)
    invited_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ("space", "phone_number") # Prevents duplicate SMS

class ActiveSpaceParticipant(models.Model):
    space = models.ForeignKey(Space, related_name="active_participants", on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=15)
    call_session_id = models.CharField(max_length=100, blank=True, null=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ("space", "phone_number")
    
    def masked_phone(self):
        return f"****{self.phone_number[-4:]}"
