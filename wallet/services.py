from django.db import transaction

from .models import SmsUsageRecord, Wallet, WalletLedgerEntry, WalletTransaction


class InsufficientCreditsError(Exception):
    """Raised when a wallet does not contain enough SMS credits."""


def _resolve_idempotency_key(idempotency_key, fallback):
    return idempotency_key or fallback


def _wallet_op_key(wallet, *, idempotency_key, payment_reference, description, transaction_type, delta_credits):
    return _resolve_idempotency_key(
        idempotency_key,
        payment_reference or f"{wallet.id}:{description}:{abs(delta_credits)}:{transaction_type}",
    )


@transaction.atomic
def _apply_wallet_delta(*, wallet, delta_credits, description, payment_reference='', payment_method='wallet', initiated_by=None, idempotency_key=None, transaction_type='deduction', amount_paid_ugx=0, usage_record=None):
    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    if wallet.balance_credits + delta_credits < 0:
        raise InsufficientCreditsError(
            f"Insufficient SMS balance ({wallet.balance_credits} available, "
            f"{abs(delta_credits)} required)."
        )

    balance_before = wallet.balance_credits
    wallet.balance_credits += delta_credits
    wallet.save(update_fields=['balance_credits', 'updated_at'])

    op_key = _wallet_op_key(
        wallet,
        idempotency_key=idempotency_key,
        payment_reference=payment_reference,
        description=description,
        transaction_type=transaction_type,
        delta_credits=delta_credits,
    )

    transaction_obj, _ = WalletTransaction.objects.get_or_create(
        wallet=wallet,
        idempotency_key=op_key,
        defaults={
            'transaction_type': transaction_type,
            'amount_paid_ugx': amount_paid_ugx,
            'credits_added': delta_credits,
            'payment_method': payment_method,
            'payment_reference': payment_reference,
            'initiated_by': initiated_by,
            'notes': description,
        },
    )

    WalletLedgerEntry.objects.get_or_create(
        wallet=wallet,
        idempotency_key=op_key,
        defaults={
            'organization': wallet.organization,
            'transaction': transaction_obj,
            'usage_record': usage_record,
            'entry_type': 'credit' if delta_credits > 0 else 'debit',
            'delta_credits': delta_credits,
            'amount_ugx': amount_paid_ugx,
            'description': description,
            'balance_before': balance_before,
            'balance_after': wallet.balance_credits,
        },
    )

    if hasattr(wallet.organization, 'sms_balance'):
        wallet.organization.sms_balance = wallet.balance_credits
        wallet.organization.save(update_fields=['sms_balance'])

    return wallet


@transaction.atomic
def reserve_sms_credits(
    *,
    organization,
    recipient_count,
    broadcast_id,
    initiated_by=None,
    notes="",
    idempotency_key=None,
):
    """Atomically reserve SMS credits and record the pending usage."""
    if recipient_count <= 0:
        raise ValueError("Recipient count must be greater than zero.")

    lock_key = _resolve_idempotency_key(idempotency_key, broadcast_id)
    existing_usage = SmsUsageRecord.objects.filter(
        wallet__organization=organization,
        idempotency_key=lock_key,
    ).first()
    if existing_usage is None:
        existing_usage = SmsUsageRecord.objects.filter(
            wallet__organization=organization,
            broadcast_id=broadcast_id,
        ).first()
    if existing_usage:
        wallet = existing_usage.wallet
        return wallet, existing_usage

    wallet = Wallet.objects.select_for_update().get(organization=organization)

    if wallet.balance_credits < recipient_count:
        raise InsufficientCreditsError(
            f"Insufficient SMS balance ({wallet.balance_credits} available, "
            f"{recipient_count} required)."
        )

    usage_record = SmsUsageRecord.objects.create(
        wallet=wallet,
        broadcast_id=broadcast_id,
        recipients_count=recipient_count,
        credits_deducted=recipient_count,
        status="pending",
        idempotency_key=lock_key,
    )

    wallet = _apply_wallet_delta(
        wallet=wallet,
        delta_credits=-recipient_count,
        description=notes or f"Reserved SMS for {recipient_count} recipients",
        payment_reference=broadcast_id,
        payment_method='wallet',
        initiated_by=initiated_by,
        idempotency_key=lock_key,
        transaction_type='deduction',
        amount_paid_ugx=0,
        usage_record=usage_record,
    )
    return wallet, usage_record


@transaction.atomic
def mark_sms_sent(usage_record_id):
    """Mark a previously reserved SMS operation as successfully sent."""
    usage_record = SmsUsageRecord.objects.select_for_update().get(pk=usage_record_id)
    usage_record.status = "sent"
    usage_record.save(update_fields=['status'])
    return usage_record


@transaction.atomic
def refund_sms_credits(*, usage_record_id, reason="SMS provider failed"):
    """Refund credits for a pending SMS operation rejected by the provider."""
    usage_record = (
        SmsUsageRecord.objects.select_for_update()
        .select_related("wallet")
        .get(pk=usage_record_id)
    )

    if usage_record.status != "pending":
        return usage_record

    wallet = Wallet.objects.select_for_update().get(pk=usage_record.wallet_id)
    credits = usage_record.credits_deducted
    lock_key = _resolve_idempotency_key(None, f"refund:{usage_record.id}:{usage_record.broadcast_id}")

    if WalletTransaction.objects.filter(
        wallet=wallet,
        payment_reference=usage_record.broadcast_id,
        payment_method='wallet_refund',
    ).exists():
        return usage_record

    wallet = _apply_wallet_delta(
        wallet=wallet,
        delta_credits=credits,
        description=reason,
        payment_reference=usage_record.broadcast_id,
        payment_method='wallet_refund',
        initiated_by=None,
        idempotency_key=lock_key,
        transaction_type='topup',
        amount_paid_ugx=0,
        usage_record=usage_record,
    )

    usage_record.status = 'failed'
    usage_record.save(update_fields=['status'])
    return usage_record
