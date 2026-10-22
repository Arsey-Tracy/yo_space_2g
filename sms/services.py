"""Application services for wallet-backed SMS broadcasts."""

from typing import Any, Callable, Optional
from uuid import uuid4

from django.utils import timezone

from account.models import CustomUser, Organization
from spaces.models import Space
from wallet.services import (
    InsufficientCreditsError,
    mark_sms_sent,
    refund_sms_credits,
    reserve_sms_credits,
)

from .models import Broadcast, SMSUsageLog
from .utils import normalize_phone_numbers

DELIVERY_FAILURE_MESSAGE = "SMS sending failed. Your SMS credits were refunded."


class SmsDeliveryError(Exception):
    """Raised when the SMS provider rejects or cannot process a broadcast."""


def deliver_broadcast(
    *,
    organization: Organization,
    space: Space,
    recipients: list[str],
    message: str,
    initiated_by: Optional[CustomUser],
    sms_sender: Callable[..., dict[str, Any]],
    broadcast_id: Optional[str] = None,
) -> None:
    """Reserve credits, send a broadcast, and finalize or refund its usage."""
    recipients = normalize_phone_numbers(recipients)
    recipient_count = len(recipients)
    if recipient_count <= 0:
        raise ValueError("At least one recipient is required.")

    usage_broadcast_id = broadcast_id or str(uuid4())

    wallet, usage_record = reserve_sms_credits(
        organization=organization,
        recipient_count=recipient_count,
        broadcast_id=usage_broadcast_id,
        initiated_by=initiated_by,
        notes=f"Broadcast to Space '{space.name}'",
    )
    try:
        result = sms_sender(
            recipients,
            message,
            sender_id=organization.sender_id,
            org_name=organization.name,
        )
        if not isinstance(result, dict) or not result.get("success"):
            error = result.get("error", "Unknown error") if isinstance(result, dict) else "Invalid provider response"
            provider_detail = " ".join(str(error).split())[:200]
            raise SmsDeliveryError(
                f"{DELIVERY_FAILURE_MESSAGE} Provider response: {provider_detail}"
            ) from RuntimeError(provider_detail)
    except Exception as exc:
        provider_error = exc.__cause__ or exc
        refund_sms_credits(
            usage_record_id=usage_record.id,
            reason=f"SMS provider failed: {provider_error}",
        )
        if isinstance(exc, SmsDeliveryError):
            raise
        raise SmsDeliveryError(DELIVERY_FAILURE_MESSAGE) from exc

    mark_sms_sent(usage_record.id)
    wallet.refresh_from_db()
    if hasattr(organization, "sms_balance"):
        organization.sms_balance = wallet.balance_credits
        organization.save(update_fields=["sms_balance"])

    SMSUsageLog.objects.create(
        organization=organization,
        recipient_count=recipient_count,
        sms_cost_credits=recipient_count,
        description=f"Broadcast to Space '{space.name}'",
    )


def deliver_scheduled_broadcast(
    *,
    broadcast: Broadcast,
    sms_sender: Callable[..., dict[str, Any]],
) -> None:
    """Deliver a claimed scheduled broadcast and persist its final state."""
    space = broadcast.space
    organization = space.organization
    recipients = normalize_phone_numbers(
        list(space.members.values_list("phone_number", flat=True))
    )
    recipient_count = len(recipients)

    deliver_broadcast(
        organization=organization,
        space=space,
        recipients=recipients,
        message=broadcast.message,
        initiated_by=broadcast.created_by,
        sms_sender=sms_sender,
        broadcast_id=f"scheduled-broadcast-{broadcast.pk}",
    )

    broadcast.status = "sent"
    broadcast.sent_at = timezone.now()
    broadcast.failure_reason = ""
    broadcast.recipients_count = recipient_count
    broadcast.cost_credits = recipient_count
    broadcast.save(
        update_fields=[
            "status",
            "sent_at",
            "failure_reason",
            "recipients_count",
            "cost_credits",
        ]
    )