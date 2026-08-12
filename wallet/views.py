import requests
from django.conf import settings
from django.db import transaction as db_transaction
from django.db.utils import OperationalError
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response

from account.models import Organization, Member
from .services import IotecPaymentService
from .models import (
    Wallet,
    WalletTransaction,
    SmsUsageRecord,
    TelecomNetwork,
    SMSBundle,
    SMSPurchase,
)
from .serializers import (
    WalletSerializer,
    WalletTransactionSerializer,
    SmsUsageRecordSerializer,
    TelecomNetworkSerializer,
    SMSBundleSerializer,
    SMSPurchaseSerializer,
    PurchaseSMSSerializer,
)


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


def compute_purchase_credits(amount_ugx):
    if amount_ugx <= 0:
        return 0
    return max(1, int(amount_ugx / getattr(settings, "SMS_PRICE_OTHER_UGX", 100)))


def confirm_purchase_from_provider(external_id):
    """Single source of truth for crediting a wallet after a top-up.
    Called from BOTH the status-poll view and the webhook -- neither one
    trusts its own caller's claimed status; both re-verify with ioTec
    directly inside this lock before crediting anything.

    select_for_update() on the purchase row means if the poll and the
    webhook fire within milliseconds of each other, the second one
    blocks until the first commits, sees status='completed', and exits
    without crediting twice.
    """
    with db_transaction.atomic():
        purchase = (
            SMSPurchase.objects
            .select_for_update()
            .select_related("organization", "organization__wallet")
            .filter(payment_reference=external_id)
            .first()
        )
        if not purchase:
            return None  # unknown reference -- nothing to credit, caller decides how to respond
        if purchase.status == "completed":
            return purchase  # already credited, no-op

        service = IotecPaymentService()
        provider_result = service.get_collection_status(external_id=external_id)
        provider_status = str(provider_result.get("status", "")).lower()

        if provider_status == "failed":
            purchase.status = "failed"
            purchase.save(update_fields=["status"])
            return purchase

        if provider_status != "success":
            return purchase  # still pending per ioTec -- do not credit

        wallet = get_or_create_wallet(purchase.organization)
        wallet.balance_credits += purchase.sms_count
        wallet.save(update_fields=["balance_credits"])

        purchase.status = "completed"
        purchase.save(update_fields=["status"])

        if hasattr(purchase.organization, "sms_balance"):
            purchase.organization.sms_balance = wallet.balance_credits
            purchase.organization.save(update_fields=["sms_balance"])

        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="topup",
            amount_paid_ugx=int(purchase.amount_paid),
            credits_added=purchase.sms_count,
            payment_method=purchase.payment_method or "Mobile Money",
            payment_reference=external_id,
            notes="Credits applied after provider-verified confirmation",
        )
        return purchase


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
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            serializer = PurchaseSMSSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            org = get_organization_for_user(request.user)
            if not org:
                return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

            bundle_id = serializer.validated_data.get("bundle_id")
            amount = serializer.validated_data.get("amount")
            bundle = SMSBundle.objects.filter(id=bundle_id, is_active=True).first() if bundle_id else None

            wallet = get_or_create_wallet(org)
            payment_method = serializer.validated_data.get("payment_method", "Mobile Money")
            phone_number = serializer.validated_data.get("phone_number", "") or serializer.validated_data.get("payment_reference", "")

            if not bundle and not amount:
                return Response({"detail": "Please select a bundle or enter a custom amount."}, status=status.HTTP_400_BAD_REQUEST)

            amount_ugx = int(bundle.price if bundle else amount)
            credits_to_add = bundle.sms_count if bundle else compute_purchase_credits(amount_ugx)

            # No embedded delimiters that collide with a fixed prefix -- avoids
            # the earlier split('-')[1] class of bug entirely by never relying
            # on parsing this string again. Lookups always go through
            # payment_reference as a plain equality match instead.
            import time as _time
            external_id = serializer.validated_data.get("external_id") or f"yospace-{org.id}-{wallet.id}-{int(_time.time())}"

            service = IotecPaymentService()
            try:
                provider_result = service.initiate_collection(
                    wallet_id=settings.IOTEC_PAY_WALLET_ID,
                    external_id=external_id,
                    amount=amount_ugx,
                    phone_number=phone_number,
                    description=f"YoSpaces top-up: {bundle.name if bundle else 'custom amount'}",
                )
            except requests.RequestException as exc:
                return Response({"detail": f"Payment provider request failed: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

            with db_transaction.atomic():
                purchase = SMSPurchase.objects.create(
                    organization=org,
                    bundle=bundle,
                    sms_count=credits_to_add,
                    amount_paid=amount_ugx,
                    status="pending",
                    payment_method=payment_method,
                    payment_reference=external_id,
                    purchased_by=request.user,
                )

            return Response({
                "message": "Payment collection initiated. Credits will be applied after confirmation.",
                "bundle": SMSBundleSerializer(bundle).data if bundle else None,
                "credits_estimate": credits_to_add,
                "current_sms_balance": wallet.balance_credits,
                "purchase": SMSPurchaseSerializer(purchase).data,
                "provider": provider_result,
            }, status=status.HTTP_201_CREATED)

        except OperationalError:
            return Response(
                {"detail": "Billing database schema not ready. Please apply migrations and retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class PaymentCollectionStatusView(APIView):
    """Frontend polls this after PurchaseSMSView. Safe to call repeatedly
    -- confirm_purchase_from_provider is idempotent."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, external_id):
        org = get_organization_for_user(request.user)
        if not org:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            purchase = confirm_purchase_from_provider(external_id)
        except requests.RequestException as exc:
            return Response({"detail": f"Payment provider request failed: {exc}"}, status=status.HTTP_502_BAD_GATEWAY)

        if not purchase or purchase.organization_id != org.id:
            return Response({"detail": "Purchase not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "organization": org.name,
            "external_id": external_id,
            "status": purchase.status,
            "wallet_balance": get_or_create_wallet(org).balance_credits,
        })


class PaymentCallbackView(APIView):
    """Public webhook target for ioTec. CRITICAL: the request body's
    claimed status is NEVER trusted directly -- it only tells us which
    external_id to go re-verify. confirm_purchase_from_provider makes its
    own authenticated call back to ioTec before crediting anything, so a
    forged POST to this endpoint cannot manufacture free credits."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        external_id = request.data.get("externalId") or request.data.get("external_id")
        if not external_id:
            return Response({"detail": "Missing external id."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            confirm_purchase_from_provider(external_id)
        except requests.RequestException as exc:
            # Still 200 -- ioTec may retry on non-2xx, and retrying won't
            # fix a network error on our side. Log it, respond OK, let the
            # next poll or retry pick it up.
            import logging
            logging.getLogger(__name__).error("Callback verification failed for %s: %s", external_id, exc)

        return Response({"received": True, "external_id": external_id})


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