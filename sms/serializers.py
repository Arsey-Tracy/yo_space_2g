from rest_framework import serializers
from .models import Broadcast

class BroadcastSerializer(serializers.ModelSerializer):
    space_name = serializers.CharField(source='space.name', read_only=True)

    class Meta:
        model = Broadcast
        fields = [
            'id', 'space', 'space_name', 'created_by', 'message', 
            'status', 'scheduled_at', 'sent_at', 'recipients_count', 
            'cost_credits', 'created_at'
        ]
        read_only_fields = ['id', 'sent_at', 'recipients_count', 'cost_credits', 'created_at']
