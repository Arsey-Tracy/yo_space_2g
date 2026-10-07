from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from .models import BroadcastSmsRecord
from wallet.models import Wallet, SmsUsageRecord
from wallet.services import (
    InsufficientCreditsError,
    reserve_sms_credits,
    mark_sms_sent,
    refund_sms_credits,
)


@transaction.atomic
def initiate_ussd_broadcast(
    *,
    space,
    phone_numbers,
    message,
    initiated_by=None,
):
    """
    Initiate a USSD broadcast SMS with proper wallet reservation.

    Flow:
    1. Reserve SMS credits from the wallet
    2. Send the bulk SMS
    3. Mark as sent on success, refund on failure

    Returns ``(broadcast_record, None)`` on success or ``(None, error_message)``
    on failure.
    """
    recipient_count = len(phone_numbers)

    if recipient_count <= 0:
        return None, "No recipients provided."

    broadcast_id = str(uuid4())

    try:
        wallet, usage_record = reserve_sms_credits(
            organization=space.organization,
            recipient_count=recipient_count,
            broadcast_id=broadcast_id,
            initiated_by=initiated_by,
            notes=f"USSD broadcast for space '{space.name}'",
        )
    except InsufficientCreditsError:
        return None, "Insufficient SMS credits in wallet."
    except Wallet.DoesNotExist:
        return None, "No wallet found for your organization. Please set one up via the web app."

    broadcast_record = BroadcastSmsRecord.objects.create(
        broadcast_id=broadcast_id,
        usage_record=usage_record,
        space=space,
        recipient_count=recipient_count,
        credits_deducted=recipient_count,
        status="pending",
    )

    from sms.views import send_bulk_sms

    result = send_bulk_sms(
        phone_numbers,
        message,
        sender_id=space.organization.sender_id if space.organization else None,
        org_name=space.organization.name if space.organization else None,
    )

    if not result.get("success"):
        refund_sms_credits(
            usage_record_id=usage_record.id,
            reason=f"SMS provider failed: {result.get('error', 'Unknown error')}",
        )
        broadcast_record.status = "refunded"
        broadcast_record.save(update_fields=["status"])
        return None, f"SMS sending failed. Your SMS credits were refunded."

    mark_sms_sent(usage_record_id=usage_record.id)

    broadcast_record.status = "sent"
    broadcast_record.sent_at = timezone.now()
    broadcast_record.save(update_fields=["status", "sent_at"])

    return broadcast_record, None


@transaction.atomic
def refund_ussd_broadcast(*, usage_record_id, reason="USSD broadcast failed"):
    """
    Refund SMS credits for a USSD broadcast that failed.
    """
    refund_sms_credits(
        usage_record_id=usage_record_id,
        reason=reason,
    )

    BroadcastSmsRecord.objects.filter(usage_record_id=usage_record_id).update(
        status="refunded"
    )

    return True
