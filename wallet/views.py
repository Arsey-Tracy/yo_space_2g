import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.db.utils import OperationalError
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

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
        defaults={
            'balance_credits': getattr(org, 'sms_balance', 0) or 0,
            'cash_balance_ugx': 0,
        },
    )
    return wallet


def compute_purchase_credits(amount_ugx):
    if amount_ugx <= 0:
        return 0
    return max(1, int(amount_ugx / 40))


class WalletViewSet(viewsets.ModelViewSet):
    """CRUD for a wallet belonging to the authenticated user's organization."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WalletSerializer

    def get_queryset(self):
        org = get_organization_for_user(self.request.user)
        if org:
            return Wallet.objects.filter(organization=org)
        return Wallet.objects.none()

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
                return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

            wallet = get_or_create_wallet(org)
            return Response({
                'organization': org.name,
                'sms_balance': wallet.balance_credits,
                'cash_balance_ugx': wallet.cash_balance_ugx,
                'updated_at': wallet.updated_at,
            })
        except OperationalError:
            return Response(
                {'detail': 'Billing database schema not ready. Please apply migrations and retry.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class SMSBundleListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            bundles = SMSBundle.objects.filter(is_active=True).order_by('price')
            serializer = SMSBundleSerializer(bundles, many=True)
            return Response(serializer.data)
        except OperationalError:
            return Response(
                {'detail': 'Billing database schema not ready. Please apply migrations and retry.'},
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
                return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

            bundle_id = serializer.validated_data.get('bundle_id')
            custom_amount = serializer.validated_data.get('custom_amount')
            bundle = None
            if bundle_id:
                bundle = SMSBundle.objects.filter(id=bundle_id, is_active=True).first()

            wallet = get_or_create_wallet(org)
            payment_method = serializer.validated_data.get('payment_method', 'Mobile Money')
            payment_reference = serializer.validated_data.get('payment_reference', '')
            phone_number = serializer.validated_data.get('phone_number', '') or payment_reference

            if not bundle and not custom_amount:
                return Response({'detail': 'Please select a bundle or enter a custom amount.'}, status=status.HTTP_400_BAD_REQUEST)

            amount_ugx = int(bundle.price if bundle else custom_amount)
            credits_to_add = compute_purchase_credits(amount_ugx)
            external_id = serializer.validated_data.get('external_id') or f"yo-space-{org.id}-{bundle_id or 'custom'}-{wallet.id}"
            service = IotecPaymentService()
            provider_result = service.initiate_collection(
                wallet_id=str(wallet.id),
                external_id=external_id,
                amount=amount_ugx,
                phone_number=phone_number,
                description=f"Yo-Spaces top-up: {'custom amount' if not bundle else bundle.name}",
            )

            with transaction.atomic():
                purchase = SMSPurchase.objects.create(
                    organization=org,
                    bundle=bundle,
                    sms_count=credits_to_add,
                    amount_paid=amount_ugx,
                    status='pending',
                    payment_method=payment_method,
                    payment_reference=external_id,
                    purchased_by=request.user,
                )

                WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type='topup',
                    amount_paid_ugx=amount_ugx,
                    credits_added=0,
                    payment_method=payment_method,
                    payment_reference=external_id,
                    initiated_by=request.user,
                    notes=f'Pending collection for {bundle.name if bundle else "custom top-up"}',
                )

            return Response({
                'message': 'Payment collection initiated. Credits will be applied after confirmation.',
                'bundle': SMSBundleSerializer(bundle).data if bundle else None,
                'credits_added': 0,
                'credits_estimate': credits_to_add,
                'new_sms_balance': wallet.balance_credits,
                'purchase': SMSPurchaseSerializer(purchase).data,
                'provider': provider_result,
            }, status=status.HTTP_201_CREATED)
        except requests.RequestException as exc:
            return Response({'detail': f'Payment provider request failed: {exc}'}, status=status.HTTP_502_BAD_GATEWAY)
        except OperationalError:
            return Response(
                {'detail': 'Billing database schema not ready. Please apply migrations and retry.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class PaymentCollectionStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, external_id):
        try:
            org = get_organization_for_user(request.user)
            if not org:
                return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

            service = IotecPaymentService()
            provider_result = service.get_collection_status(external_id=external_id)
            status_value = str(provider_result.get('status', '')).lower()

            if status_value == 'success':
                wallet = get_or_create_wallet(org)
                purchase = SMSPurchase.objects.filter(
                    organization=org,
                    payment_reference__in=[external_id, provider_result.get('requestId')],
                ).order_by('-purchased_at').first()
                if purchase and purchase.status != 'completed':
                    with transaction.atomic():
                        purchase.status = 'completed'
                        purchase.save(update_fields=['status'])
                        wallet.balance_credits += purchase.sms_count
                        wallet.save(update_fields=['balance_credits'])

                        if hasattr(org, 'sms_balance'):
                            org.sms_balance = wallet.balance_credits
                            org.save(update_fields=['sms_balance'])

                        WalletTransaction.objects.create(
                            wallet=wallet,
                            transaction_type='topup',
                            amount_paid_ugx=int(purchase.amount_paid),
                            credits_added=purchase.sms_count,
                            payment_method=purchase.payment_method or 'Mobile Money',
                            payment_reference=external_id,
                            initiated_by=request.user,
                            notes='Credits applied after provider confirmation',
                        )

            return Response({
                'organization': org.name,
                'external_id': external_id,
                'provider_status': provider_result.get('status'),
                'wallet_balance': get_or_create_wallet(org).balance_credits,
            })
        except requests.RequestException as exc:
            return Response({'detail': f'Payment provider request failed: {exc}'}, status=status.HTTP_502_BAD_GATEWAY)
        except OperationalError:
            return Response(
                {'detail': 'Billing database schema not ready. Please apply migrations and retry.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class PaymentCallbackView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        external_id = request.data.get('externalId') or request.data.get('external_id')
        status_value = str(request.data.get('status') or request.data.get('transactionStatus') or '').lower()

        if not external_id:
            return Response({'detail': 'Missing external id.'}, status=status.HTTP_400_BAD_REQUEST)

        org = Organization.objects.filter(id=external_id.split('-')[1] if len(external_id.split('-')) > 1 else None).first() if '-' in external_id else None
        if not org:
            org = None

        if status_value == 'success' and org:
            wallet = get_or_create_wallet(org)
            purchase = SMSPurchase.objects.filter(
                organization=org,
                payment_reference__in=[external_id],
            ).order_by('-purchased_at').first()
            if purchase and purchase.status != 'completed':
                with transaction.atomic():
                    purchase.status = 'completed'
                    purchase.save(update_fields=['status'])
                    wallet.balance_credits += purchase.sms_count
                    wallet.save(update_fields=['balance_credits'])

                    if hasattr(org, 'sms_balance'):
                        org.sms_balance = wallet.balance_credits
                        org.save(update_fields=['sms_balance'])

                    WalletTransaction.objects.create(
                        wallet=wallet,
                        transaction_type='topup',
                        amount_paid_ugx=int(purchase.amount_paid),
                        credits_added=purchase.sms_count,
                        payment_method=purchase.payment_method or 'Mobile Money',
                        payment_reference=external_id,
                        initiated_by=None,
                        notes='Credits applied from payment callback',
                    )

        return Response({'received': True, 'external_id': external_id, 'status': status_value})


class SMSPurchaseHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            org = get_organization_for_user(request.user)
            if not org:
                return Response([], status=status.HTTP_200_OK)
            purchases = SMSPurchase.objects.filter(organization=org).order_by('-purchased_at')
            return Response(SMSPurchaseSerializer(purchases, many=True).data)
        except OperationalError:
            return Response(
                {'detail': 'Billing database schema not ready. Please apply migrations and retry.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class WalletTransactionViewSet(viewsets.ModelViewSet):
    """List and create wallet transactions for the user's wallet."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WalletTransactionSerializer

    def get_queryset(self):
        org = get_organization_for_user(self.request.user)
        wallet = getattr(org, 'wallet', None) if org else None
        if wallet:
            return WalletTransaction.objects.filter(wallet=wallet)
        return WalletTransaction.objects.none()

    def perform_create(self, serializer):
        org = get_organization_for_user(self.request.user)
        wallet = get_or_create_wallet(org) if org else None
        if not org or not wallet:
            raise PermissionError("User must have a wallet to record a transaction.")
        serializer.save(wallet=wallet, initiated_by=self.request.user)


class SmsUsageRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """Read‑only viewset for SMS usage records linked to the user's wallet."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SmsUsageRecordSerializer

    def get_queryset(self):
        org = get_organization_for_user(self.request.user)
        wallet = getattr(org, 'wallet', None) if org else None
        if wallet:
            return SmsUsageRecord.objects.filter(wallet=wallet)
        return SmsUsageRecord.objects.none()


class TelecomNetworkViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for Telecom Network pricing rules."""
    permission_classes = [permissions.AllowAny]
    serializer_class = TelecomNetworkSerializer

    def get_queryset(self):
        return TelecomNetwork.objects.filter(is_active=True)

