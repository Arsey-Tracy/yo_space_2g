from django.test import TestCase

from account.models import CustomUser, Organization
from wallet.models import Wallet, WalletTransaction
from wallet.services import (
    InsufficientCreditsError,
    mark_sms_sent,
    refund_sms_credits,
    reserve_sms_credits,
)


class WalletSMSCreditTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="wallet_test",
            password="testpassword123",
        )
        self.organization = Organization.objects.create(
            owner=self.user,
            name="Wallet Test Organization",
        )
        self.wallet = Wallet.objects.create(
            organization=self.organization,
            balance_credits=100,
            cash_balance_ugx=0,
        )

    def test_reserve_sms_credits(self):
        wallet, usage = reserve_sms_credits(
            organization=self.organization,
            recipient_count=20,
            broadcast_id="test-broadcast-1",
            initiated_by=self.user,
        )

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_credits, 80)
        self.assertEqual(usage.credits_deducted, 20)
        self.assertEqual(usage.status, "pending")

        transaction = WalletTransaction.objects.get(
            payment_reference="test-broadcast-1"
        )
        self.assertEqual(transaction.credits_added, -20)
        self.assertEqual(transaction.transaction_type, "deduction")

    def test_cannot_spend_more_than_wallet_balance(self):
        with self.assertRaises(InsufficientCreditsError):
            reserve_sms_credits(
                organization=self.organization,
                recipient_count=101,
                broadcast_id="test-broadcast-2",
                initiated_by=self.user,
            )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_credits, 100)

    def test_mark_sms_sent(self):
        _, usage = reserve_sms_credits(
            organization=self.organization,
            recipient_count=10,
            broadcast_id="test-broadcast-3",
            initiated_by=self.user,
        )

        mark_sms_sent(usage.id)
        usage.refresh_from_db()
        self.assertEqual(usage.status, "sent")

    def test_failed_sms_refunds_credits(self):
        _, usage = reserve_sms_credits(
            organization=self.organization,
            recipient_count=25,
            broadcast_id="test-broadcast-4",
            initiated_by=self.user,
        )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_credits, 75)

        refund_sms_credits(
            usage_record_id=usage.id,
            reason="Provider failure",
        )

        self.wallet.refresh_from_db()
        usage.refresh_from_db()
        self.assertEqual(self.wallet.balance_credits, 100)
        self.assertEqual(usage.status, "failed")
        self.assertTrue(
            WalletTransaction.objects.filter(
                payment_reference="test-broadcast-4",
                payment_method="wallet_refund",
                credits_added=25,
            ).exists()
        )
