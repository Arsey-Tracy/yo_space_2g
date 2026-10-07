import logging

from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from account.models import Organization
from wallet.services import InsufficientCreditsError

from .models import Broadcast
from .permissions import IsOrganizationOwner
from .serializers import BroadcastSerializer
from .services import SmsDeliveryError, deliver_broadcast
from .providers import format_sms_message, send_bulk_sms

logger = logging.getLogger("yospaces")


class BroadcastViewSet(viewsets.ModelViewSet):
    permission_classes = [
        permissions.IsAuthenticated,
        IsOrganizationOwner,
    ]
    serializer_class = BroadcastSerializer

    def create(self, request, *args, **kwargs):
        space_id = request.data.get("space")
        if space_id is not None:
            try:
                from spaces.models import Space as SpaceModel

                space = SpaceModel.objects.get(id=space_id)
            except SpaceModel.DoesNotExist:
                return Response(
                    {"detail": "Space not found."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not space.organization or space.organization.owner_id != request.user.id:
                return Response(
                    {
                        "detail": "You do not have permission to create broadcast for this organization."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return super().create(request, *args, **kwargs)

    def get_queryset(self):
        return Broadcast.objects.filter(
            space__organization__owner=self.request.user
        ).select_related("space", "space__organization", "created_by")

    def perform_create(self, serializer):
        space = serializer.validated_data["space"]
        organization = Organization.objects.filter(
            owner=self.request.user,
            id=space.organization_id,
        ).first()
        if not organization:
            raise ValidationError(
                "You do not have permission to send SMS from this Space"
            )
        raw_message = serializer.validated_data["message"]
        broadcast_status = serializer.validated_data.get("status", "draft")
        message = format_sms_message(
            raw_message,
            sender_id=organization.sender_id,
            org_name=organization.name,
        )

        recipients = list(space.members.values_list("phone_number", flat=True))
        recipients_count = len(recipients)

        if broadcast_status == "sent":
            if recipients_count == 0:
                raise ValidationError("At least one recipient is required.")
            try:
                deliver_broadcast(
                    organization=organization,
                    space=space,
                    recipients=recipients,
                    message=message,
                    initiated_by=self.request.user,
                    sms_sender=send_bulk_sms,
                )
            except InsufficientCreditsError as exc:
                raise ValidationError(str(exc)) from exc
            except SmsDeliveryError as exc:
                raise ValidationError(str(exc)) from exc

            serializer.save(
                created_by=self.request.user,
                message=message,
                recipients_count=recipients_count,
                cost_credits=recipients_count,
                sent_at=timezone.now(),
                status="sent",
            )
        else:
            serializer.save(
                created_by=self.request.user,
                message=message,
                recipients_count=recipients_count,
                cost_credits=recipients_count,
                status=broadcast_status,
            )


@csrf_exempt
def sms_delivery_report(request):
    """
    Africa's Talking SMS Delivery Report Webhook
    """
    if request.method == "POST":
        msg_id = request.POST.get("id")
        status_text = request.POST.get("status")
        phone_number = request.POST.get("phoneNumber")
        logger.info(
            "SMS DLR Received - ID: %s, Phone: %s, Status: %s",
            msg_id,
            phone_number,
            status_text,
        )
        return HttpResponse("OK", content_type="text/plain")
    return HttpResponse("DLR Webhook Ready", content_type="text/plain")
