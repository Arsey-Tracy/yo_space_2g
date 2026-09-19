from django.test import TestCase, TransactionTestCase

from account.models import CustomUser, Organization
from wallet.models import SmsUsageRecord, Wallet, WalletTransaction
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
        self.organization.sms_balance = 100
        self.organization.save(update_fields=["sms_balance"])

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

    def test_provider_failure_refunds_credits(self):
        initial_balance = self.wallet.balance_credits

        usage_record = SmsUsageRecord.objects.create(
            wallet=self.wallet,
            broadcast_id="test-provider-failure",
            recipients_count=10,
            credits_deducted=10,
            status="pending",
        )

        self.wallet.balance_credits -= 10
        self.wallet.save(update_fields=["balance_credits", "updated_at"])

        refund_sms_credits(
            usage_record_id=usage_record.id,
            reason="SMS provider failed",
        )

        self.wallet.refresh_from_db()
        usage_record.refresh_from_db()

        self.assertEqual(
            self.wallet.balance_credits,
            initial_balance,
        )

        self.assertEqual(
            usage_record.status,
            "failed",
        )

        self.assertTrue(
            WalletTransaction.objects.filter(
                wallet=self.wallet,
                payment_method="wallet_refund",
                credits_added=10,
            ).exists()
        )

    def test_provider_exception_refunds_credits(self):
        initial_balance = self.wallet.balance_credits

        usage_record = reserve_sms_credits(
            organization=self.organization,
            recipient_count=10,
            broadcast_id="test-provider-exception",
            initiated_by=self.user,
        )[1]

        self.wallet.refresh_from_db()

        self.assertEqual(
            self.wallet.balance_credits,
            initial_balance - 10,
        )

        refund_sms_credits(
            usage_record_id=usage_record.id,
            reason="SMS provider exception: connection timeout",
        )

        self.wallet.refresh_from_db()
        usage_record.refresh_from_db()

        self.assertEqual(
            self.wallet.balance_credits,
            initial_balance,
        )

        self.assertEqual(
            usage_record.status,
            "failed",
        )

    def test_refund_cannot_happen_twice(self):
        initial_balance = self.wallet.balance_credits

        usage_record = reserve_sms_credits(
            organization=self.organization,
            recipient_count=10,
            broadcast_id="test-double-refund",
            initiated_by=self.user,
        )[1]

        self.wallet.refresh_from_db()

        self.assertEqual(
            self.wallet.balance_credits,
            initial_balance - 10,
        )

        refund_sms_credits(
            usage_record_id=usage_record.id,
            reason="First refund",
        )

        self.wallet.refresh_from_db()

        self.assertEqual(
            self.wallet.balance_credits,
            initial_balance,
        )

        refund_sms_credits(
            usage_record_id=usage_record.id,
            reason="Second refund",
        )

        self.wallet.refresh_from_db()

        self.assertEqual(
            self.wallet.balance_credits,
            initial_balance,
        )

        refund_count = WalletTransaction.objects.filter(
            wallet=self.wallet,
            payment_method="wallet_refund",
            payment_reference="test-double-refund",
        ).count()

        self.assertEqual(refund_count, 1)

    def test_refund_syncs_organization_sms_balance(self):
        usage_record = reserve_sms_credits(
            organization=self.organization,
            recipient_count=10,
            broadcast_id="test-org-balance-sync",
            initiated_by=self.user,
        )[1]

        self.wallet.refresh_from_db()
        self.organization.refresh_from_db()

        refund_sms_credits(
            usage_record_id=usage_record.id,
            reason="Provider failed",
        )

        self.wallet.refresh_from_db()
        self.organization.refresh_from_db()

        self.assertEqual(
            self.organization.sms_balance,
            self.wallet.balance_credits,
        )


class WalletTransactionTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="txn_test",
            password="testpassword123",
        )
        self.organization = Organization.objects.create(
            owner=self.user,
            name="Wallet Transaction Test Organization",
            sms_balance=100,
        )
        self.wallet = Wallet.objects.create(
            organization=self.organization,
            balance_credits=100,
            cash_balance_ugx=0,
        )

    def test_reservation_transaction_updates_wallet(self):
        wallet = Wallet.objects.get(organization=self.organization)

        wallet.balance_credits = 100
        wallet.save(update_fields=["balance_credits", "updated_at"])

        wallet, usage_record = reserve_sms_credits(
            organization=self.organization,
            recipient_count=80,
            broadcast_id="transaction-lock-test",
            initiated_by=self.user,
        )

        wallet.refresh_from_db()

        self.assertEqual(wallet.balance_credits, 20)
        self.assertEqual(usage_record.status, "pending")
