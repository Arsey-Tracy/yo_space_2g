from rest_framework import serializers

from .models import ContactMessage


class ContactMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = [
            'id', 'name', 'email', 'phone', 'organization',
            'inquiry_type', 'message', 'is_read', 'created_at',
        ]
        read_only_fields = ['id', 'is_read', 'created_at']
