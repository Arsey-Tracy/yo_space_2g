import logging
import urllib.parse
import urllib.request
from typing import Optional

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status, permissions, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from account.models import Organization
from .permissions import IsOrganizationOwner
from .models import SMSUsageLog, Broadcast
from .serializers import BroadcastSerializer
from wallet.models import SmsUsageRecord
from wallet.services import mark_sms_sent, refund_sms_credits, reserve_sms_credits
from uuid import uuid4

try:
    import africastalking  # type: ignore
except Exception:  # pragma: no cover
    africastalking = None

logger = logging.getLogger("yospaces")

AFRICASTALKING_LIVE_USERNAME = getattr(
    settings, "AFRICASTALKING_LIVE_USERNAME", "yo_space"
)
AFRICASTALKING_LIVE_API_KEY = getattr(settings, "AFRICASTALKING_LIVE_API_KEY", "")

if africastalking and AFRICASTALKING_LIVE_API_KEY:
    try:
        africastalking.initialize(
            AFRICASTALKING_LIVE_USERNAME, AFRICASTALKING_LIVE_API_KEY
        )
    except Exception as exc:
        logger.warning("Africa's Talking SDK initialization failed in SMS app: %s", exc)


def _normalize_phone(phone: str) -> str:
    phone = (phone or "").strip().replace(" ", "")
    if not phone:
        return phone
    if phone.startswith("+"):
        return phone
    if phone.startswith("0"):
        return "+256" + phone[1:]
    return "+" + phone


def send_bulk_sms(
    phone_numbers: list[str],
    message: str,
    sender_id: Optional[str] = None,
    org_name: Optional[str] = None,
) -> dict:
    """
    Sends bulk SMS via Africa's Talking API and returns result dictionary.
    Includes Organization Name prefix if custom sender ID is not set.
    """
    # Prepend Organization Name if sender_id is not set or custom sender ID is disabled
    if org_name and not sender_id and not message.startswith(f"[{org_name}]"):
        message = f"[{org_name}]: {message}"

    normalized_recipients = list(set(_normalize_phone(p) for p in phone_numbers if p))
    if not normalized_recipients:
        return {
            "success": False,
            "error": "No valid recipient phone numbers provided.",
            "count": 0,
        }

    if africastalking and AFRICASTALKING_LIVE_API_KEY:
        try:
            sms_client = getattr(africastalking, "SMS", None)
            if sms_client and hasattr(sms_client, "send"):
                kwargs = {"message": message, "recipients": normalized_recipients}
                if sender_id:
                    kwargs["sender_id"] = sender_id
                response = sms_client.send(**kwargs)
                logger.info("Africa's Talking SMS response: %s", response)
                return {
                    "success": True,
                    "response": response,
                    "count": len(normalized_recipients),
                }
        except Exception as exc:
            logger.error("Africa's Talking SDK SMS error: %s", exc)

    # REST Fallback
    try:
        url = "https://api.africastalking.com/version1/messaging"
        payload_data = {
            "username": AFRICASTALKING_LIVE_USERNAME,
            "to": ",".join(normalized_recipients),
            "message": message,
        }
        if sender_id:
            payload_data["from"] = sender_id

        payload = urllib.parse.urlencode(payload_data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Accept", "application/json")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        req.add_header("apiKey", AFRICASTALKING_LIVE_API_KEY)

        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return {
                "success": True,
                "response": body,
                "count": len(normalized_recipients),
            }
    except Exception as exc:
        logger.error("REST SMS Fallback failed: %s", exc)
        return {
            "success": False,
            "error": str(exc),
            "count": len(normalized_recipients),
        }


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

        # Auto-prefix org name if sender ID is absent
        message = raw_message
        if (
            organization
            and organization.name
            and not organization.sender_id
            and not message.startswith(f"[{organization.name}]")
        ):
            message = f"[{organization.name}]: {raw_message}"

        recipients = list(space.members.values_list("phone_number", flat=True))
        recipients_count = len(recipients)

        if broadcast_status == "sent":
            broadcast_id = str(uuid4())
            try:
                wallet, usage_record = reserve_sms_credits(
                    organization=organization,
                    recipient_count=recipients_count,
                    broadcast_id=broadcast_id,
                    initiated_by=self.request.user,
                    notes=f"Broadcast to Space '{space.name}'",
                )
            except Exception as exc:
                from wallet.services import InsufficientCreditsError

                if isinstance(exc, InsufficientCreditsError):
                    raise ValidationError(str(exc))
                raise

            try:
                res = send_bulk_sms(
                    recipients,
                    message,
                    sender_id=organization.sender_id,
                    org_name=organization.name,
                )
            except Exception as exc:
                refund_sms_credits(
                    usage_record_id=usage_record.id,
                    reason=f"SMS provider exception: {str(exc)}",
                )

                raise ValidationError(
                    "SMS sending failed. Your SMS credits were refunded."
                )

            if not res.get("success"):
                refund_sms_credits(
                    usage_record_id=usage_record.id,
                    reason=f"SMS provider failed: {res.get('error', 'Unknown error')}",
                )
                raise ValidationError(
                    "SMS sending failed. Your SMS credits were refunded."
                )

            mark_sms_sent(usage_record.id)
            wallet.refresh_from_db()

            if hasattr(organization, "sms_balance"):
                organization.sms_balance = wallet.balance_credits
                organization.save(update_fields=["sms_balance"])

            SMSUsageLog.objects.create(
                organization=organization,
                recipient_count=recipients_count,
                sms_cost_credits=recipients_count,
                description=f"Broadcast to Space '{space.name}'",
            )

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
        phoneNumber = request.POST.get("phoneNumber")
        logger.info(
            "SMS DLR Received - ID: %s, Phone: %s, Status: %s",
            msg_id,
            phoneNumber,
            status_text,
        )
        return HttpResponse("OK", content_type="text/plain")
    return HttpResponse("DLR Webhook Ready", content_type="text/plain")
