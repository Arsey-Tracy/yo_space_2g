import requests
import logging

from .helpers import compute_purchase_credits, normalize_phone_number_e164
from django.conf import settings
from django.db import transaction as db_transaction
from django.db.utils import OperationalError
from django.utils import timezone

from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from uuid import uuid4
from urllib.parse import urlencode

from account.models import Organization, Member
from .marzpay_service import MarzpayError, MarzpayService
from .models import (
    Wallet,
    WalletTransaction,
    SmsUsageRecord,
    TelecomNetwork,
    SMSBundle,
    SMSPurchase,
    MarzpayPayment
)
from .serializers import (
    WalletSerializer,
    WalletTransactionSerializer,
    SmsUsageRecordSerializer,
    TelecomNetworkSerializer,
    SMSBundleSerializer,
    SMSPurchaseSerializer,
    SendSMSSerializer,
    MarzpayPaymentSerializer, 
    InitiateMarzpayPaymentSerializer
)

logger = logging.getLogger(__name__)

def get_organization_for_user(user):
    org = Organization.objects.filter(owner=user).first()
    if org:
        return org
    member = Member.objects.filter(user=user).first()
    return member.organization if member else None


def get_or_create_wallet(org):
    wallet, _ = Wallet.objects.get_or_create(
        organization=org,
        defaults={"balance_credits": getattr(org, "sms_balance", 0) or 0, "cash_balance_ugx": 0},
    )
    return wallet

class WalletViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WalletSerializer

    def get_queryset(self):
        org = get_organization_for_user(self.request.user)
        return Wallet.objects.filter(organization=org) if org else Wallet.objects.none()

    def perform_create(self, serializer):
        org = get_organization_for_user(self.request.user)
        if not org:
            raise PermissionError("User must belong to an organization to create a wallet.")
        serializer.save(organization=org)


class WalletBalanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            org = get_organization_for_user(request.user)
            if not org:
                return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
            wallet = get_or_create_wallet(org)
            return Response({
                "organization": org.name,
                "sms_balance": wallet.balance_credits,
                "cash_balance_ugx": wallet.cash_balance_ugx,
                "updated_at": wallet.updated_at,
            })
        except OperationalError:
            return Response(
                {"detail": "Billing database schema not ready. Please apply migrations and retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class SMSBundleListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            bundles = SMSBundle.objects.filter(is_active=True).order_by("price")
            return Response(SMSBundleSerializer(bundles, many=True).data)
        except OperationalError:
            return Response(
                {"detail": "Billing database schema not ready. Please apply migrations and retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class PurchaseSMSView(APIView):
    """Initiate SMS bundle purchase via MarzPay (wallet top-up)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            org = get_organization_for_user(request.user)
            if not org:
                return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

            data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
            if "custom_amount" in data and "amount" not in data:
                data["amount"] = data.pop("custom_amount")
            if not data.get("email"):
                data["email"] = getattr(request.user, "email", "") or ""

            serializer = InitiateMarzpayPaymentSerializer(data=data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            bundle_id = serializer.validated_data.get("bundle_id")
            bundle = None
            if bundle_id:
                bundle = SMSBundle.objects.filter(id=bundle_id, is_active=True).first()
                if not bundle:
                    return Response({"detail": "Bundle not found."}, status=status.HTTP_404_NOT_FOUND)
                amount_ugx = int(bundle.price)
                sms_count = bundle.sms_count
                description = f"SMS Credits - {bundle.name}"
            else:
                amount_ugx = int(serializer.validated_data["amount"])
                sms_price = getattr(settings, "SMS_PRICE_OTHER_UGX", 50)
                sms_count = max(1, int(amount_ugx / sms_price))
                description = serializer.validated_data.get("description", f"SMS Credits - {sms_count} SMS")

            phone_e164 = normalize_phone_number_e164(serializer.validated_data["phone_number"])
            reference = str(uuid4())  # MarzPay requires UUID v4

            with db_transaction.atomic():
                sms_purchase = SMSPurchase.objects.create(
                    organization=org,
                    bundle=bundle,
                    sms_count=sms_count,
                    amount_paid=amount_ugx,
                    status="pending",
                    payment_method="marzpay",
                    payment_reference=reference,
                    purchased_by=request.user,
                )
                
                marzpay_payment = MarzpayPayment.objects.create(
                    organization=org,
                    amount=amount_ugx,
                    currency="UGX",
                    reference=reference,
                    customer_phone=phone_e164,
                    description=description,
                    sms_purchase=sms_purchase,
                    status="initiated"
                )

            service = MarzpayService()
            api_res = service.initiate_collection(
                amount=amount_ugx,
                phone_number=phone_e164,
                reference=reference,
                description=description,
                callback_url=getattr(settings, 'MARZPAY_CALLBACK_URL', '')
            )

            # Store returned transaction UUID
            txn_uuid = api_res.get("data", {}).get("transaction", {}).get("uuid")
            marzpay_payment.transaction_uuid = txn_uuid
            marzpay_payment.status = "processing"
            marzpay_payment.save(update_fields=["transaction_uuid", "status"])

            return Response({
                "message": "Mobile money payment prompt sent. Please approve on your phone.",
                "reference": reference,
                "transaction_uuid": txn_uuid,
                "payment": MarzpayPaymentSerializer(marzpay_payment).data,
            }, status=status.HTTP_201_CREATED)

        except MarzpayError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("MarzPay initiation failed: %s", exc)
            return Response({"detail": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except OperationalError as exc:
            logger.error("Database error: %s", exc)
            return Response(
                {"detail": "Database error. Please retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

class SMSPurchaseHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            org = get_organization_for_user(request.user)
            if not org:
                return Response([], status=status.HTTP_200_OK)
            purchases = SMSPurchase.objects.filter(organization=org).order_by("-purchased_at")
            return Response(SMSPurchaseSerializer(purchases, many=True).data)
        except OperationalError:
            return Response(
                {"detail": "Billing database schema not ready. Please apply migrations and retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class WalletTransactionViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WalletTransactionSerializer

    def get_queryset(self):
        org = get_organization_for_user(self.request.user)
        wallet = getattr(org, "wallet", None) if org else None
        return WalletTransaction.objects.filter(wallet=wallet) if wallet else WalletTransaction.objects.none()

    def perform_create(self, serializer):
        org = get_organization_for_user(self.request.user)
        wallet = get_or_create_wallet(org) if org else None
        if not org or not wallet:
            raise PermissionError("User must have a wallet to record a transaction.")
        serializer.save(wallet=wallet, initiated_by=self.request.user)


class SmsUsageRecordViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SmsUsageRecordSerializer

    def get_queryset(self):
        org = get_organization_for_user(self.request.user)
        wallet = getattr(org, "wallet", None) if org else None
        return SmsUsageRecord.objects.filter(wallet=wallet) if wallet else SmsUsageRecord.objects.none()


class TelecomNetworkViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.AllowAny]
    serializer_class = TelecomNetworkSerializer

    def get_queryset(self):
        return TelecomNetwork.objects.filter(is_active=True)

class SendSMSView(APIView):
    """Send SMS and deduct from wallet."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            serializer = SendSMSSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            org = get_organization_for_user(request.user)
            if not org:
                return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

            recipients = serializer.validated_data["recipients"]
            message = serializer.validated_data["message"]
            broadcast_id = serializer.validated_data.get("broadcast_id") or str(uuid4())

            # Get wallet
            wallet = get_or_create_wallet(org)
            
            # Check balance
            if wallet.balance_credits < len(recipients):
                return Response({
                    "detail": f"Insufficient SMS balance. Required: {len(recipients)}, Available: {wallet.balance_credits}",
                    "required": len(recipients),
                    "available": wallet.balance_credits,
                }, status=status.HTTP_400_BAD_REQUEST)

            # Import SMS sending function
            from sms.views import send_bulk_sms

            # Send SMS
            result = send_bulk_sms(
                recipients,
                message,
                sender_id=getattr(org, "sender_id", None),
                org_name=org.name,
            )

            if not result.get("success"):
                return Response({
                    "detail": f"SMS sending failed: {result.get('error', 'Unknown error')}",
                    "error": result.get("error"),
                }, status=status.HTTP_400_BAD_REQUEST)

            # Deduct from wallet
            with db_transaction.atomic():
                wallet.balance_credits -= len(recipients)
                wallet.save(update_fields=["balance_credits"])

                # Create usage record
                usage_record = SmsUsageRecord.objects.create(
                    wallet=wallet,
                    broadcast_id=broadcast_id,
                    recipients_count=len(recipients),
                    credits_deducted=len(recipients),
                    status="sent",
                )

                # Create transaction record
                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type="deduction",
                    amount_paid_ugx=0,
                    credits_added=-len(recipients),
                    payment_method="wallet",
                    payment_reference=broadcast_id,
                    notes=f"SMS broadcast to {len(recipients)} recipients",
                )

                # Update organization
                if hasattr(org, "sms_balance"):
                    org.sms_balance = wallet.balance_credits
                    org.save(update_fields=["sms_balance"])

            return Response({
                "message": f"SMS sent successfully to {len(recipients)} recipients",
                "broadcast_id": broadcast_id,
                "recipients_count": len(recipients),
                "credits_deducted": len(recipients),
                "remaining_balance": wallet.balance_credits,
                "provider_response": result.get("response"),
            }, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.exception("Failed to send SMS: %s", exc)
            return Response(
                {"detail": f"Error: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

def apply_completed_marzpay_payment(marzpay_payment: MarzpayPayment, provider_tx_id: str = None) -> MarzpayPayment:
    """Idempotently credit organization wallet after MarzPay reports completed collection."""
    payment_id = marzpay_payment.pk
    with db_transaction.atomic():
        # 1. Fetch ID first (no lock) to avoid outer join issues with select_for_update
        target_id = MarzpayPayment.objects.filter(pk=payment_id).values_list('pk', flat=True).first()
        if not target_id:
            return marzpay_payment

        # 2. Lock specifically by ID on the base table only
        payment = MarzpayPayment.objects.select_for_update().get(pk=target_id)

        purchase = payment.sms_purchase
        if purchase:
            # Lock the purchase separately on its base table to avoid join locking issues
            purchase = SMSPurchase.objects.select_for_update().get(pk=purchase.pk)

        if purchase and purchase.status == "completed":
            payment.status = "completed"
            if provider_tx_id:
                payment.provider_transaction_id = provider_tx_id
            payment.save(update_fields=["status", "provider_transaction_id", "last_updated_at"])
            return payment

        credits = purchase.sms_count if purchase else compute_purchase_credits(int(payment.amount or 0))
        wallet = get_or_create_wallet(payment.organization)
        wallet.balance_credits += credits
        wallet.save(update_fields=["balance_credits"])

        if purchase:
            purchase.status = "completed"
            purchase.payment_method = "marzpay"
            purchase.save(update_fields=["status", "payment_method"])

        org = payment.organization
        if hasattr(org, "sms_balance"):
            org.sms_balance = wallet.balance_credits
            org.save(update_fields=["sms_balance"])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="topup",
            amount_paid_ugx=int(payment.amount or 0),
            credits_added=credits,
            payment_method="marzpay",
            payment_reference=payment.reference,
            notes=f"MarzPay Mobile Money payment ({payment.reference})",
        )

        payment.status = "completed"
        payment.completed_at = timezone.now()
        if provider_tx_id:
            payment.provider_transaction_id = provider_tx_id
        payment.save(update_fields=["status", "completed_at", "provider_transaction_id", "last_updated_at"])

    return MarzpayPayment.objects.get(pk=payment_id)


class InitiateMarzpayPaymentView(APIView):
    """Initiate a MarzPay mobile money prompt for SMS top-up."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            org = get_organization_for_user(request.user)
            if not org:
                return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

            serializer = InitiateMarzpayPaymentSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            bundle_id = serializer.validated_data.get("bundle_id")
            bundle = None
            if bundle_id:
                bundle = SMSBundle.objects.filter(id=bundle_id, is_active=True).first()
                if not bundle:
                    return Response({"detail": "Bundle not found."}, status=status.HTTP_404_NOT_FOUND)
                amount_ugx = int(bundle.price)
                sms_count = bundle.sms_count
                description = f"SMS Credits - {bundle.name}"
            else:
                amount_ugx = int(serializer.validated_data["amount"])
                sms_price = getattr(settings, "SMS_PRICE_OTHER_UGX", 50)
                sms_count = max(1, int(amount_ugx / sms_price))
                description = serializer.validated_data.get("description", f"SMS Credits - {sms_count} SMS")

            phone_e164 = normalize_phone_number_e164(serializer.validated_data["phone_number"])
            reference = str(uuid4())  # MarzPay requires UUID v4

            with db_transaction.atomic():
                sms_purchase = SMSPurchase.objects.create(
                    organization=org,
                    bundle=bundle,
                    sms_count=sms_count,
                    amount_paid=amount_ugx,
                    status="pending",
                    payment_method="marzpay",
                    payment_reference=reference,
                    purchased_by=request.user,
                )
                
                marzpay_payment = MarzpayPayment.objects.create(
                    organization=org,
                    amount=amount_ugx,
                    currency="UGX",
                    reference=reference,
                    customer_phone=phone_e164,
                    description=description,
                    sms_purchase=sms_purchase,
                    status="initiated"
                )

            service = MarzpayService()
            api_res = service.initiate_collection(
                amount=amount_ugx,
                phone_number=phone_e164,
                reference=reference,
                description=description,
                callback_url=getattr(settings, 'MARZPAY_CALLBACK_URL', '')
            )

            # Store returned transaction UUID
            txn_uuid = api_res.get("data", {}).get("transaction", {}).get("uuid")
            marzpay_payment.transaction_uuid = txn_uuid
            marzpay_payment.status = "processing"
            marzpay_payment.save(update_fields=["transaction_uuid", "status"])

            return Response({
                "message": "Mobile money payment prompt sent. Please approve on your phone.",
                "reference": reference,
                "transaction_uuid": txn_uuid,
                "payment": MarzpayPaymentSerializer(marzpay_payment).data,
            }, status=status.HTTP_201_CREATED)

        except MarzpayError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("MarzPay initiation failed: %s", exc)
            return Response({"detail": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MarzpayCallbackView(APIView):
    """Webhook callback endpoint for MarzPay payment notifications."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        try:
            body = request.data
            # Extract payload whether wrapped in dashboard `{ data: ... }` envelope or direct
            payload = body.get("data") if isinstance(body.get("data"), dict) and "transaction" in body.get("data") else body

            event_type = payload.get("event_type") or body.get("event_type")
            transaction_data = payload.get("transaction", {})
            collection_data = payload.get("collection", {})

            reference = transaction_data.get("reference")
            provider_tx_id = collection_data.get("provider_transaction_id")

            if not reference:
                return Response({"detail": "Missing reference in webhook payload"}, status=status.HTTP_400_BAD_REQUEST)

            payment = MarzpayPayment.objects.filter(reference=reference).first()
            if not payment:
                logger.warning("MarzPay webhook received for unknown reference: %s", reference)
                return Response({"received": True}, status=status.HTTP_200_OK)

            payment.webhook_data = body
            payment.save(update_fields=["webhook_data"])

            if event_type == "collection.completed":
                apply_completed_marzpay_payment(payment, provider_tx_id=provider_tx_id)
            elif event_type in ["collection.failed", "collection.cancelled"]:
                payment.status = "failed"
                payment.save(update_fields=["status"])
                if payment.sms_purchase:
                    payment.sms_purchase.status = "failed"
                    payment.sms_purchase.save(update_fields=["status"])

            return Response({"received": True}, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.exception("Error processing MarzPay webhook: %s", exc)
            return Response({"received": True}, status=status.HTTP_200_OK)


class MarzpayPaymentStatusView(APIView):
    """Poll transaction status by reference.

    Webhooks are the primary way a payment gets marked completed, but they can
    be delayed, dropped, or unreachable (e.g. no public HTTPS callback URL in
    local/dev environments). While the payment is still in flight, this view
    actively verifies the transaction directly against the MarzPay API and
    credits the wallet immediately if MarzPay reports it as completed, instead
    of waiting indefinitely on a webhook that may never arrive.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, reference):
        org = get_organization_for_user(request.user)
        if not org:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        payment = MarzpayPayment.objects.filter(reference=reference, organization=org).first()
        if not payment:
            return Response({"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND)

        if payment.status in ("initiated", "processing") and payment.transaction_uuid:
            try:
                service = MarzpayService()
                api_res = service.get_transaction_status(payment.transaction_uuid)
                data = api_res.get("data", {}) if isinstance(api_res, dict) else {}
                txn = data.get("transaction", {}) or {}
                collection = data.get("collection", {}) or {}
                provider_status = txn.get("status")
                provider_tx_id = collection.get("provider_transaction_id")

                if provider_status == "completed":
                    payment = apply_completed_marzpay_payment(payment, provider_tx_id=provider_tx_id)
                elif provider_status in ("failed", "cancelled"):
                    payment.status = "failed"
                    payment.save(update_fields=["status", "last_updated_at"])
                    if payment.sms_purchase:
                        payment.sms_purchase.status = "failed"
                        payment.sms_purchase.save(update_fields=["status"])
            except MarzpayError as exc:
                logger.warning("MarzPay status verification failed for %s: %s", reference, exc)

        return Response({
            "reference": reference,
            "status": payment.status,
            "wallet_balance": get_or_create_wallet(org).balance_credits,
            "payment": MarzpayPaymentSerializer(payment).data,
        })