from django.db import transaction

from .models import SmsUsageRecord, Wallet, WalletTransaction


class InsufficientCreditsError(Exception):
    """Raised when a wallet does not contain enough SMS credits."""


@transaction.atomic
def reserve_sms_credits(
    *,
    organization,
    recipient_count,
    broadcast_id,
    initiated_by=None,
    notes="",
):
    """Atomically reserve SMS credits and record the pending usage."""
    if recipient_count <= 0:
        raise ValueError("Recipient count must be greater than zero.")

    wallet = Wallet.objects.select_for_update().get(organization=organization)

    if wallet.balance_credits < recipient_count:
        raise InsufficientCreditsError(
            f"Insufficient SMS balance ({wallet.balance_credits} available, "
            f"{recipient_count} required)."
        )

    wallet.balance_credits -= recipient_count
    wallet.save(update_fields=["balance_credits", "updated_at"])

    usage_record = SmsUsageRecord.objects.create(
        wallet=wallet,
        broadcast_id=broadcast_id,
        recipients_count=recipient_count,
        credits_deducted=recipient_count,
        status="pending",
    )

    WalletTransaction.objects.create(
        wallet=wallet,
        transaction_type="deduction",
        amount_paid_ugx=0,
        credits_added=-recipient_count,
        payment_method="wallet",
        payment_reference=broadcast_id,
        initiated_by=initiated_by,
        notes=notes or f"Reserved SMS for {recipient_count} recipients",
    )

    return wallet, usage_record


@transaction.atomic
def mark_sms_sent(usage_record_id):
    """Mark a previously reserved SMS operation as successfully sent."""
    usage_record = SmsUsageRecord.objects.select_for_update().get(pk=usage_record_id)
    usage_record.status = "sent"
    usage_record.save(update_fields=["status"])
    return usage_record


@transaction.atomic
def refund_sms_credits(*, usage_record_id, reason="SMS provider failed"):
    """Refund credits for a pending SMS operation rejected by the provider."""
    usage_record = (
        SmsUsageRecord.objects.select_for_update()
        .select_related("wallet")
        .get(pk=usage_record_id)
    )
    
    # Prevent double refunds
    if usage_record.status != "pending":
        return usage_record

    wallet = Wallet.objects.select_for_update().get(pk=usage_record.wallet_id)
    credits = usage_record.credits_deducted
    wallet.balance_credits += credits
    wallet.save(update_fields=["balance_credits", "updated_at"])
    
    # Keep the legacy organisation balance synchronized
    # while Organization balance still exists
    organization = wallet.organization
    
    if hasattr(organization, "sms_balance"):
        organization.sms_balance = wallet.balance_credits
        organization.save(update_fields=["sms_balance"])

    WalletTransaction.objects.create(
        wallet=wallet,
        transaction_type="topup",
        amount_paid_ugx=0,
        credits_added=credits,
        payment_method="wallet_refund",
        payment_reference=usage_record.broadcast_id,
        notes=reason,
    )

    usage_record.status = "failed"
    usage_record.save(update_fields=["status"])
    return usage_record
