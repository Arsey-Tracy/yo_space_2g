from django.db import transaction
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from account.models import Organization, Member
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


class SMSBundleListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        bundles = SMSBundle.objects.filter(is_active=True).order_by('price')
        serializer = SMSBundleSerializer(bundles, many=True)
        return Response(serializer.data)


class PurchaseSMSView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PurchaseSMSSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        org = get_organization_for_user(request.user)
        if not org:
            return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        bundle = SMSBundle.objects.filter(id=serializer.validated_data['bundle_id'], is_active=True).first()
        if not bundle:
            return Response({'detail': 'SMS bundle not found or no longer available.'}, status=status.HTTP_404_NOT_FOUND)

        wallet = get_or_create_wallet(org)
        payment_method = serializer.validated_data.get('payment_method', 'Mobile Money')
        payment_reference = serializer.validated_data.get('payment_reference', '')

        with transaction.atomic():
            purchase = SMSPurchase.objects.create(
                organization=org,
                bundle=bundle,
                sms_count=bundle.sms_count,
                amount_paid=bundle.price,
                status='completed',
                payment_method=payment_method,
                payment_reference=payment_reference,
                purchased_by=request.user,
            )

            wallet.balance_credits += bundle.sms_count
            wallet.save(update_fields=['balance_credits'])

            WalletTransaction.objects.create(
                wallet=wallet,
                transaction_type='topup',
                amount_paid_ugx=int(bundle.price),
                credits_added=bundle.sms_count,
                payment_method=payment_method,
                payment_reference=payment_reference,
                initiated_by=request.user,
                notes=f'Purchased bundle {bundle.name}',
            )

        return Response({
            'message': f'{bundle.sms_count} SMS credits purchased successfully!',
            'bundle': SMSBundleSerializer(bundle).data,
            'credits_added': bundle.sms_count,
            'new_sms_balance': wallet.balance_credits,
            'purchase': SMSPurchaseSerializer(purchase).data,
        }, status=status.HTTP_201_CREATED)


class SMSPurchaseHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org = get_organization_for_user(request.user)
        if not org:
            return Response([], status=status.HTTP_200_OK)
        purchases = SMSPurchase.objects.filter(organization=org).order_by('-purchased_at')
        return Response(SMSPurchaseSerializer(purchases, many=True).data)


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

