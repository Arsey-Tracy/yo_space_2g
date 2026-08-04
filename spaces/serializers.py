from rest_framework import serializers
from .models import Space, SpaceMember, ActiveSpaceParticipant


class SpaceMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpaceMember
        fields = ['id', 'space', 'user', 'name', 'phone_number', 'role', 'joined_at']
        read_only_fields = ['id', 'space', 'joined_at']


class SpaceSerializer(serializers.ModelSerializer):
    members_count = serializers.SerializerMethodField()
    active_listeners_count = serializers.SerializerMethodField()

    class Meta:
        model = Space
        fields = [
            'id', 'organization', 'name', 'description', 'host_phone', 
            'pin', 'is_public', 'is_active', 'members_count', 
            'active_listeners_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'organization', 'host_phone', 'pin', 'created_at', 'updated_at']

    def get_members_count(self, obj):
        return obj.members.count()

    def get_active_listeners_count(self, obj):
        return obj.active_participants.count()


class MergeSpacesSerializer(serializers.Serializer):
    source_space_id = serializers.IntegerField()
    target_space_id = serializers.IntegerField()
    keep_source_space = serializers.BooleanField(default=False)
