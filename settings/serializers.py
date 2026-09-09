from rest_framework import serializers

from .models import OrganizationSetting


class OrganizationSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationSetting
        fields = [
            'id',
            'organization',
            'company_name',
            'default_language',
            'sms_sender_id',
            'email_notifications',
            'sms_notifications',
            'voice_enabled',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'organization', 'created_at', 'updated_at']
