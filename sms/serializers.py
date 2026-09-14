from rest_framework import serializers
from .models import Broadcast
from spaces.models import Space


class BroadcastSerializer(serializers.ModelSerializer):
    space_name = serializers.CharField(source="space.name", read_only=True)

    class Meta:
        model = Broadcast
        fields = [
            "id",
            "space",
            "space_name",
            "created_by",
            "message",
            "status",
            "scheduled_at",
            "sent_at",
            "recipients_count",
            "cost_credits",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "sent_at",
            "recipients_count",
            "cost_credits",
            "created_at",
        ]

    def validate_space(self, space):
        request = self.context["request"]
        if not space.organization:
            raise serializers.ValidationError(
                "This Space is not associated with an organiation."
            )
        if space.organization.owner_id != request.user.id:
            raise serializers.ValidationError(
                "You do not have permission to ue this Space."
            )
        return space
