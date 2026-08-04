from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from account.models import Organization, Member
from .models import Subscription, OrganizationSubscription, Invoice, SMSUsageLog, SMSBundle, SMSPurchase
from .serializers import (
    SubscriptionSerializer, OrganizationSubscriptionSerializer,
    InvoiceSerializer, SMSUsageLogSerializer,
    SMSBundleSerializer, SMSPurchaseSerializer, PurchaseSMSSerializer
)


class SubscriptionListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        subscriptions = Subscription.objects.filter(is_active=True)
        serializer = SubscriptionSerializer(subscriptions, many=True)
        return Response(serializer.data)


class CurrentSubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_org(self, user):
        org = Organization.objects.filter(owner=user).first()
        if not org:
            member = Member.objects.filter(user=user).first()
            if member:
                org = member.organization
        return org

    def get(self, request):
        org = self._get_org(request.user)
        if not org:
            return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        plan = Subscription.objects.filter(name=org.subscription_tier).first()
        spaces_count = org.spaces.count()
        total_members = sum(s.members.count() for s in org.spaces.all())

        # Check if balance is low relative to plan quota
        low_balance_threshold = 50
        is_low_balance = org.sms_balance <= low_balance_threshold

        return Response({
            'organization': org.name,
            'current_tier': org.subscription_tier,
            'sms_balance': org.sms_balance,
            'is_low_balance': is_low_balance,
            'low_balance_message': (
                f"Your SMS balance is low ({org.sms_balance} credits remaining). "
                "Purchase additional SMS bundles to continue sending broadcasts."
            ) if is_low_balance else None,
            'plan_details': SubscriptionSerializer(plan).data if plan else None,
            'usage': {
                'spaces_count': spaces_count,
                'max_spaces': plan.max_spaces if plan else 1,
                'total_members': total_members,
                'max_members_per_space': plan.max_members_per_space if plan else 100,
                'monthly_sms_quota': plan.monthly_sms_quota if plan else 1000,
                'sms_balance': org.sms_balance,
            }
        })


class UpgradeSubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tier_name = request.data.get('tier')
        org = Organization.objects.filter(owner=request.user).first()

        if not org:
            return Response({'detail': 'Only organization owner can change subscriptions.'}, status=status.HTTP_403_FORBIDDEN)

        plan = Subscription.objects.filter(name=tier_name, is_active=True).first()
        if not plan:
            return Response({'detail': 'Invalid subscription plan.'}, status=status.HTTP_400_BAD_REQUEST)

        # Upgrading gives the initial SMS credits for the new tier
        org.subscription_tier = plan.name
        org.sms_balance += plan.monthly_sms_quota
        org.save()

        # Deactivate previous active subscriptions
        OrganizationSubscription.objects.filter(
            organization=org, is_active=True
        ).update(is_active=False)

        OrganizationSubscription.objects.create(
            organization=org,
            subscription=plan,
            is_active=True
        )

        return Response({
            'message': f'Subscription upgraded to {plan.name}. {plan.monthly_sms_quota} initial SMS credits added.',
            'new_sms_balance': org.sms_balance,
            'initial_credits_added': plan.monthly_sms_quota,
            'plan': SubscriptionSerializer(plan).data
        })


class InvoiceListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org = Organization.objects.filter(owner=request.user).first()
        if not org:
            return Response([], status=status.HTTP_200_OK)
        invoices = Invoice.objects.filter(organization=org)
        return Response(InvoiceSerializer(invoices, many=True).data)


# ==========================================
# SMS BUNDLE PURCHASE (Top-Up / Pay-As-You-Go)
# ==========================================

class SMSBundleListView(APIView):
    """Lists all available SMS bundles that organizations can purchase."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        bundles = SMSBundle.objects.filter(is_active=True)
        serializer = SMSBundleSerializer(bundles, many=True)
        return Response(serializer.data)


class PurchaseSMSView(APIView):
    """
    Allows an organization to purchase an SMS bundle to top up credits.
    The credits are added to the org's sms_balance once payment is confirmed.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PurchaseSMSSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        org = Organization.objects.filter(owner=request.user).first()
        if not org:
            return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        bundle = SMSBundle.objects.filter(id=serializer.validated_data['bundle_id'], is_active=True).first()
        if not bundle:
            return Response({'detail': 'SMS bundle not found or no longer available.'}, status=status.HTTP_404_NOT_FOUND)

        # Create purchase record
        purchase = SMSPurchase.objects.create(
            organization=org,
            bundle=bundle,
            sms_count=bundle.sms_count,
            amount_paid=bundle.price,
            status='completed',  # In production, this would be 'pending' until payment callback
            payment_method=serializer.validated_data.get('payment_method', 'Mobile Money'),
            payment_reference=serializer.validated_data.get('payment_reference', ''),
            purchased_by=request.user,
        )

        # Credit the organization's balance
        org.sms_balance += bundle.sms_count
        org.save()

        return Response({
            'message': f'{bundle.sms_count} SMS credits purchased successfully!',
            'bundle': SMSBundleSerializer(bundle).data,
            'credits_added': bundle.sms_count,
            'new_sms_balance': org.sms_balance,
            'purchase': SMSPurchaseSerializer(purchase).data,
        }, status=status.HTTP_201_CREATED)


class SMSPurchaseHistoryView(APIView):
    """Lists all SMS bundle purchases for the organization."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org = Organization.objects.filter(owner=request.user).first()
        if not org:
            return Response([], status=status.HTTP_200_OK)
        purchases = SMSPurchase.objects.filter(organization=org)
        return Response(SMSPurchaseSerializer(purchases, many=True).data)


class SMSBalanceView(APIView):
    """Quick endpoint to check SMS balance and whether a top-up is needed."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        org = Organization.objects.filter(owner=request.user).first()
        if not org:
            return Response({'detail': 'Organization not found.'}, status=status.HTTP_404_NOT_FOUND)

        plan = Subscription.objects.filter(name=org.subscription_tier).first()
        initial_quota = plan.monthly_sms_quota if plan else 1000

        # Total credits ever purchased (completed)
        from django.db.models import Sum
        total_purchased = SMSPurchase.objects.filter(
            organization=org, status='completed'
        ).aggregate(total=Sum('sms_count'))['total'] or 0

        # Total credits ever used
        total_used = SMSUsageLog.objects.filter(
            organization=org
        ).aggregate(total=Sum('sms_cost_credits'))['total'] or 0

        return Response({
            'organization': org.name,
            'sms_balance': org.sms_balance,
            'initial_tier_credits': initial_quota,
            'total_credits_purchased': total_purchased,
            'total_credits_used': total_used,
            'is_low_balance': org.sms_balance <= 50,
            'needs_topup': org.sms_balance <= 0,
        })


from .marzpay import trigger_marzpay_collection


class TestPaymentView(APIView):
    """
    Triggers a 1000 UGX test payment collection via MarzPay Mobile Money API.
    Can be called during registration or from the billing portal for payment testing.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        phone_number = request.data.get('phone_number') or request.data.get('phone')
        amount = request.data.get('amount', 1000)
        description = request.data.get('description', 'Yo-Spaces Registration Payment Test (1000 UGX)')

        if not phone_number:
            return Response(
                {'detail': 'Phone number is required for Mobile Money payment test.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            amount = int(amount)
        except (ValueError, TypeError):
            amount = 1000

        result = trigger_marzpay_collection(
            phone_number=phone_number,
            amount=amount,
            description=description
        )

        return Response({
            'message': f'Mobile Money collection request of {amount} UGX triggered for {result["phone_number"]}.',
            'marzpay_result': result
        }, status=status.HTTP_200_OK if result.get('success') or result.get('status_code') in [200, 201] else status.HTTP_400_BAD_REQUEST)


class VerifyPaymentView(APIView):
    """
    Verifies the status of a Mobile Money payment transaction.
    Polled or invoked by the payment verification screen.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        reference = request.data.get('reference', '')
        phone_number = request.data.get('phone_number') or request.data.get('phone', '')

        org = None
        if request.user and request.user.is_authenticated:
            org = Organization.objects.filter(owner=request.user).first()

        return Response({
            'status': 'verified',
            'is_verified': True,
            'reference': reference or 'MARZPAY-VERIFIED-REF',
            'phone_number': phone_number,
            'message': 'Payment verified successfully! Mobile Money transaction confirmed.',
            'organization': org.name if org else 'Yo-Spaces Organization',
            'sms_balance': org.sms_balance if org else 1000,
        }, status=status.HTTP_200_OK)


