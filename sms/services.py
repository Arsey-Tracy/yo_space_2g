"""Application services for wallet-backed SMS broadcasts."""

from typing import Any, Callable
from uuid import uuid4

from account.models import CustomUser, Organization
from spaces.models import Space
from wallet.services import (
    InsufficientCreditsError,
    mark_sms_sent,
    refund_sms_credits,
    reserve_sms_credits,
)

from .models import SMSUsageLog

DELIVERY_FAILURE_MESSAGE = "SMS sending failed. Your SMS credits were refunded."


class SmsDeliveryError(Exception):
    """Raised when the SMS provider rejects or cannot process a broadcast."""


def deliver_broadcast(
    *,
    organization: Organization,
    space: Space,
    recipients: list[str],
    message: str,
    initiated_by: CustomUser,
    sms_sender: Callable[..., dict[str, Any]],
) -> None:
    """Reserve credits, send a broadcast, and finalize or refund its usage."""
    recipient_count = len(recipients)
    if recipient_count <= 0:
        raise ValueError("At least one recipient is required.")

    broadcast_id = str(uuid4())

    try:
        wallet, usage_record = reserve_sms_credits(
            organization=organization,
            recipient_count=recipient_count,
            broadcast_id=broadcast_id,
            initiated_by=initiated_by,
            notes=f"Broadcast to Space '{space.name}'",
        )
    except InsufficientCreditsError:
        raise
    try:
        result = sms_sender(
            recipients,
            message,
            sender_id=organization.sender_id,
            org_name=organization.name,
        )
        if not isinstance(result, dict) or not result.get("success"):
            error = result.get("error", "Unknown error") if isinstance(result, dict) else "Invalid provider response"
            raise SmsDeliveryError(DELIVERY_FAILURE_MESSAGE) from RuntimeError(error)
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