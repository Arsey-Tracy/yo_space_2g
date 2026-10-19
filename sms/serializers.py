from django.utils import timezone
from rest_framework import serializers

from .models import Broadcast


class BroadcastSerializer(serializers.ModelSerializer):
    """API representation and ownership validation for SMS broadcasts."""

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
            "failure_reason",
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
            "failure_reason",
        ]

    def validate_space(self, space):
        request = self.context["request"]
        if not space.organization:
            raise serializers.ValidationError(
                "This Space is not associated with an organization."
            )
        if space.organization.owner_id != request.user.id:
            raise serializers.ValidationError(
                "You do not have permission to use this Space."
            )
        return space

    def validate(self, attrs):
        status_value = attrs.get(
            "status", self.instance.status if self.instance else "draft"
        )
        scheduled_at = attrs.get(
            "scheduled_at", self.instance.scheduled_at if self.instance else None
        )

        if status_value == "scheduled":
            if scheduled_at is None:
                raise serializers.ValidationError(
                    {"scheduled_at": "A scheduled broadcast requires a send time."}
                )
            if scheduled_at <= timezone.now():
                raise serializers.ValidationError(
                    {"scheduled_at": "Choose a future send time."}
                )
        elif scheduled_at is not None:
            raise serializers.ValidationError(
                {"scheduled_at": "Only scheduled broadcasts may have a send time."}
            )

        if self.instance:
            if attrs.get("status", self.instance.status) != self.instance.status:
                raise serializers.ValidationError(
                    {"status": "Broadcast status is managed by the delivery system."}
                )
            if (
                "space" in attrs
                and attrs["space"].pk != self.instance.space_id
            ):
                raise serializers.ValidationError(
                    {"space": "The target Space cannot be changed after creation."}
                )
            if self.instance.status in {"sending", "sent", "failed"} and attrs:
                raise serializers.ValidationError(
                    "This broadcast can no longer be edited."
                )
        elif status_value not in {"draft", "scheduled", "sent"}:
            raise serializers.ValidationError(
                {"status": "Broadcasts can only be created as draft, scheduled, or sent."}
            )

        return attrs
