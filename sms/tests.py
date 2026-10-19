from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from account.models import CustomUser, Organization
from spaces.models import Space, SpaceMember
from sms.models import Broadcast, SMSUsageLog
from sms.providers import format_sms_message, send_bulk_sms
from sms.services import SmsDeliveryError, deliver_broadcast
from wallet.models import SmsUsageRecord, Wallet


class BroadcastSecurityTests(APITestCase):
    def setUp(self):
        self.user_a = CustomUser.objects.create_user(
            username="org_a",
            phone="0707567890",
            password="test-password",
        )
        self.user_b = CustomUser.objects.create_user(
            username="org_b",
            phone="0778136778",
            password="test-password",
        )
        self.org_a = Organization.objects.create(
            owner=self.user_a,
            name="Organization A",
        )
        self.org_b = Organization.objects.create(
            owner=self.user_b,
            name="Organization B",
        )
        self.space_b = Space.objects.create(
            organization=self.org_b,
            name="Private Space B",
        )

    def test_user_cannot_create_broadcast_for_another_organization(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(
            "/api/sms/broadcasts/",
            {
                "space": self.space_b.id,
                "message": "This should not be sent.",
                "status": "draft",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("permission", response.data.get("detail", "").lower())


class SmsProviderTests(SimpleTestCase):
    def test_format_sms_message_prefixes_only_when_sender_id_is_missing(self):
        self.assertEqual(
            format_sms_message("Hello", org_name="Community"),
            "[Community]: Hello",
        )
        self.assertEqual(
            format_sms_message(
                "Hello",
                sender_id="COMMUNITY",
                org_name="Community",
            ),
            "Hello",
        )
        self.assertEqual(
            format_sms_message("[Community]: Hello", org_name="Community"),
            "[Community]: Hello",
        )

    @patch("sms.providers._send_with_rest_api")
    @patch("sms.providers.africastalking", None)
    @patch("sms.providers.AFRICASTALKING_API_KEY", "")
    def test_send_bulk_sms_normalizes_and_deduplicates_recipients(self, send_rest):
        send_rest.return_value = {"success": True, "count": 2}

        result = send_bulk_sms(
            ["0700000001", "+256700000002", "0700000001"],
            "Hello",
            org_name="Community",
        )

        self.assertTrue(result["success"])
        send_rest.assert_called_once_with(
            ["+256700000001", "+256700000002"],
            "[Community]: Hello",
            None,
        )

    def test_send_bulk_sms_rejects_empty_recipients_without_provider_call(self):
        with patch("sms.providers._send_with_rest_api") as send_rest:
            result = send_bulk_sms(["", "  "], "Hello")

        self.assertFalse(result["success"])
        self.assertEqual(result["count"], 0)
        send_rest.assert_not_called()


class SmsBroadcastServiceTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            username="sms_owner",
            phone="0700000001",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            owner=self.owner,
            name="Community",
        )
        self.space = Space.objects.create(
            organization=self.organization,
            name="Community Space",
        )
        self.wallet = Wallet.objects.create(
            organization=self.organization,
            balance_credits=5,
        )

    def test_deliver_broadcast_marks_usage_sent_and_deducts_credits(self):
        deliver_broadcast(
            organization=self.organization,
            space=self.space,
            recipients=["+256700000002", "+256700000003"],
            message="Hello",
            initiated_by=self.owner,
            sms_sender=lambda *args, **kwargs: {"success": True},
        )

        self.wallet.refresh_from_db()
        usage = SmsUsageRecord.objects.get()
        self.assertEqual(self.wallet.balance_credits, 3)
        self.assertEqual(usage.status, "sent")
        self.assertEqual(SMSUsageLog.objects.get().recipient_count, 2)

    def test_deliver_broadcast_only_charges_unique_normalized_recipients(self):
        deliver_broadcast(
            organization=self.organization,
            space=self.space,
            recipients=[
                "0700000002",
                "+256700000002",
                "0700000003",
            ],
            message="Hello",
            initiated_by=self.owner,
            sms_sender=lambda *args, **kwargs: {"success": True},
        )

        self.wallet.refresh_from_db()
        usage = SmsUsageRecord.objects.get()
        self.assertEqual(self.wallet.balance_credits, 3)
        self.assertEqual(usage.recipients_count, 2)
        self.assertEqual(SMSUsageLog.objects.get().recipient_count, 2)

    def test_deliver_broadcast_refunds_credits_when_provider_rejects(self):
        with self.assertRaises(SmsDeliveryError):
            deliver_broadcast(
                organization=self.organization,
                space=self.space,
                recipients=["+256700000002"],
                message="Hello",
                initiated_by=self.owner,
                sms_sender=lambda *args, **kwargs: {
                    "success": False,
                    "error": "Provider unavailable",
                },
            )

        self.wallet.refresh_from_db()
        usage = SmsUsageRecord.objects.get()
        self.assertEqual(self.wallet.balance_credits, 5)
        self.assertEqual(usage.status, "failed")
        self.assertFalse(SMSUsageLog.objects.exists())

    def test_deliver_broadcast_requires_recipients(self):
        with self.assertRaisesMessage(ValueError, "At least one recipient"):
            deliver_broadcast(
                organization=self.organization,
                space=self.space,
                recipients=[],
                message="Hello",
                initiated_by=self.owner,
                sms_sender=lambda *args, **kwargs: {"success": True},
            )


class ScheduledBroadcastTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            username="scheduled_owner",
            phone="0700000004",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            owner=self.owner,
            name="Scheduled Community",
        )
        self.space = Space.objects.create(
            organization=self.organization,
            name="Scheduled Space",
        )
        self.wallet = Wallet.objects.create(
            organization=self.organization,
            balance_credits=5,
        )
        self.broadcast = Broadcast.objects.create(
            space=self.space,
            created_by=self.owner,
            message="Scheduled message",
            scheduled_at=timezone.now() - timedelta(minutes=1),
            status="scheduled",
        )

    @patch("sms.management.commands.process_scheduled_broadcasts.send_bulk_sms")
    def test_command_sends_due_broadcast_and_updates_wallet(self, send_sms):
        SpaceMember.objects.create(
            space=self.space,
            phone_number="0700000005",
        )
        SpaceMember.objects.create(
            space=self.space,
            phone_number="+256700000005",
        )
        send_sms.return_value = {"success": True}

        output = StringIO()
        call_command("process_scheduled_broadcasts", stdout=output)

        self.broadcast.refresh_from_db()
        self.wallet.refresh_from_db()
        self.assertEqual(self.broadcast.status, "sent")
        self.assertIsNotNone(self.broadcast.sent_at)
        self.assertEqual(self.broadcast.recipients_count, 1)
        self.assertEqual(self.wallet.balance_credits, 4)
        self.assertIn("1 sent, 0 failed", output.getvalue())

    @patch("sms.management.commands.process_scheduled_broadcasts.send_bulk_sms")
    def test_command_marks_provider_failures_and_refunds_credits(self, send_sms):
        SpaceMember.objects.create(
            space=self.space,
            phone_number="0700000006",
        )
        send_sms.return_value = {"success": False, "error": "Provider unavailable"}

        call_command("process_scheduled_broadcasts", stderr=StringIO())

        self.broadcast.refresh_from_db()
        self.wallet.refresh_from_db()
        self.assertEqual(self.broadcast.status, "failed")
        self.assertIn("SMS sending failed", self.broadcast.failure_reason)
        self.assertEqual(self.wallet.balance_credits, 5)

    @patch("sms.management.commands.process_scheduled_broadcasts.send_bulk_sms")
    def test_command_fails_broadcast_when_space_has_no_recipients(self, send_sms):
        call_command("process_scheduled_broadcasts", stderr=StringIO())

        self.broadcast.refresh_from_db()
        self.assertEqual(self.broadcast.status, "failed")
        self.assertIn("At least one recipient", self.broadcast.failure_reason)
        send_sms.assert_not_called()

    def test_command_rejects_non_positive_limit(self):
        with self.assertRaisesMessage(
            CommandError,
            "--limit must be a positive integer.",
        ):
            call_command("process_scheduled_broadcasts", limit=0)


class BroadcastApiValidationTests(APITestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            username="broadcast_api_owner",
            phone="0700000007",
            password="test-password",
        )
        self.organization = Organization.objects.create(
            owner=self.owner,
            name="API Community",
        )
        self.space = Space.objects.create(
            organization=self.organization,
            name="API Space",
        )
        self.client.force_authenticate(user=self.owner)

    def test_scheduled_broadcast_requires_a_future_send_time(self):
        response = self.client.post(
            "/api/sms/broadcasts/",
            {
                "space": self.space.id,
                "message": "Future message",
                "status": "scheduled",
                "scheduled_at": (timezone.now() - timedelta(minutes=1)).isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("scheduled_at", response.data)

    def test_api_accepts_a_future_scheduled_broadcast(self):
        scheduled_at = timezone.now() + timedelta(days=1)
        response = self.client.post(
            "/api/sms/broadcasts/",
            {
                "space": self.space.id,
                "message": "Future message",
                "status": "scheduled",
                "scheduled_at": scheduled_at.isoformat(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "scheduled")
        self.assertEqual(response.data["recipients_count"], 0)
        self.assertEqual(Broadcast.objects.count(), 1)

    def test_scheduled_broadcast_requires_a_send_time(self):
        response = self.client.post(
            "/api/sms/broadcasts/",
            {
                "space": self.space.id,
                "message": "Missing schedule",
                "status": "scheduled",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("scheduled_at", response.data)

    def test_api_cannot_create_a_broadcast_in_a_worker_managed_state(self):
        response = self.client.post(
            "/api/sms/broadcasts/",
            {
                "space": self.space.id,
                "message": "Forged sent message",
                "status": "sending",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_api_cannot_change_status_after_broadcast_creation(self):
        create_response = self.client.post(
            "/api/sms/broadcasts/",
            {
                "space": self.space.id,
                "message": "Draft message",
                "status": "draft",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        update_response = self.client.patch(
            f"/api/sms/broadcasts/{create_response.data['id']}/",
            {"status": "sent"},
            format="json",
        )

        self.assertEqual(update_response.status_code, status.HTTP_400_BAD_REQUEST)
