# pyrefly: ignore [missing-import]
from rest_framework import viewsets, permissions
# pyrefly: ignore [import-error]
from account.models import Organization
# pyrefly: ignore [import-error, missing-import]
from .models import Wallet, WalletTransaction, SmsUsageRecord
# pyrefly: ignore [import-error, missing-import]
from .serializers import WalletSerializer, WalletTransactionSerializer, SmsUsageRecordSerializer, TelecomNetworkSerializer


class WalletViewSet(viewsets.ModelViewSet):
    """CRUD for a wallet belonging to the authenticated user's organization."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WalletSerializer

    def get_queryset(self):
        org = Organization.objects.filter(owner=self.request.user).first()
        if org:
            return Wallet.objects.filter(organization=org)
        return Wallet.objects.none()

    def perform_create(self, serializer):
        org = Organization.objects.filter(owner=self.request.user).first()
        if not org:
            raise PermissionError("User must belong to an organization to create a wallet.")
        serializer.save(organization=org)


class WalletTransactionViewSet(viewsets.ModelViewSet):
    """List and create wallet transactions for the user's wallet."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WalletTransactionSerializer

    def get_queryset(self):
        org = Organization.objects.filter(owner=self.request.user).first()
        if org and hasattr(org, 'wallet'):
            return WalletTransaction.objects.filter(wallet=org.wallet)
        return WalletTransaction.objects.none()

    def perform_create(self, serializer):
        org = Organization.objects.filter(owner=self.request.user).first()
        if not org or not hasattr(org, 'wallet'):
            raise PermissionError("User must have a wallet to record a transaction.")
        serializer.save(wallet=org.wallet, initiated_by=self.request.user)


class SmsUsageRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """Read‑only viewset for SMS usage records linked to the user's wallet."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SmsUsageRecordSerializer

    def get_queryset(self):
        org = Organization.objects.filter(owner=self.request.user).first()
        if org and hasattr(org, 'wallet'):
            return SmsUsageRecord.objects.filter(wallet=org.wallet)
        return SmsUsageRecord.objects.none()


class TelecomNetworkViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset for Telecom Network pricing rules."""
    permission_classes = [permissions.AllowAny]
    serializer_class = TelecomNetworkSerializer

    def get_queryset(self):
        from .models import TelecomNetwork
        return TelecomNetwork.objects.filter(is_active=True)

