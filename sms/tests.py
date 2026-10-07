# from django.test import TestCase
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from account.models import CustomUser, Organization
from spaces.models import Space
from sms.models import SMSUsageLog
from sms.providers import format_sms_message, send_bulk_sms
from sms.services import SmsDeliveryError, deliver_broadcast
from wallet.models import SmsUsageRecord, Wallet


class BroadcastSecurityTests(APITestCase):
    def setUp(self):
        self.user_a = CustomUser.objects.create_user(username="org_a",
            phone="0707567890",
            password="#testpassword123",
        )
        self.user_b = CustomUser.objects.create_user(username="org_b",
            phone="0778136778",
            password="testpassword123",
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
            organization=self.org_b, name="Private Space B"
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
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertIn("permission", response.data.get("detail", "").lower())


class SmsProviderTests(SimpleTestCase):
    def test_format_sms_message_prefixes_only_when_sender_id_is_missing(self):
        self.assertEqual(
            format_sms_message("Hello", org_name="Community"),
            "[Community]: Hello",
        )
        self.assertEqual(
            format_sms_message("Hello", sender_id="COMMUNITY", org_name="Community"),
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
            password="testpassword123",
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
