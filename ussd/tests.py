from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from account.models import CustomUser, Organization
from spaces.models import Space, SpaceMember
from survey.models import Survey, SurveyQuestion
from wallet.models import Wallet
from ussd.models import UssdSession, BroadcastSmsRecord
from ussd.services import initiate_ussd_broadcast, refund_ussd_broadcast
from ussd.views import _is_host, _normalize_phone


# ==========================================
# Host detection
# ==========================================


class UssdHostDetectionTests(TestCase):
    """Tests for the fixed ``_is_host`` logic (update.md §2)."""

    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            username="host_owner",
            phone="+256700111111",
            password="pass123",
        )
        self.org = Organization.objects.create(
            owner=self.owner, name="Host Org", sms_balance=100
        )

    def test_org_owner_is_detected_as_host(self):
        self.assertTrue(_is_host("+256700111111"))

    def test_regular_user_with_phone_is_not_host(self):
        regular = CustomUser.objects.create_user(
            username="regular_user",
            phone="+256700222222",
            password="pass123",
        )
        self.assertFalse(_is_host("+256700222222"))

    def test_space_host_without_org_owner_phone_is_not_host(self):
        """A host_phone on a Space whose org-owner phone differs must not
        grant host privileges to that phone number."""
        Space.objects.create(
            organization=self.org,
            name="Stranger Space",
            host_phone="+256799999999",
        )
        self.assertFalse(_is_host("+256799999999"))

    def test_space_host_with_matching_org_owner_is_host(self):
        Space.objects.create(
            organization=self.org,
            name="Owned Space",
            host_phone="+256700111111",
        )
        self.assertTrue(_is_host("+256700111111"))


# ==========================================
# Session model
# ==========================================


class UssdSessionModelTests(TestCase):
    """Tests for persistent ``UssdSession`` (update.md §1)."""

    def test_session_has_default_state_and_expiry(self):
        session = UssdSession.objects.create(
            phone_number="+256700111111",
        )
        self.assertEqual(session.state, "main_menu")
        self.assertIsNotNone(session.expires_at)
        self.assertTrue(session.expires_at > timezone.now())

    def test_cleanup_expired_removes_only_expired(self):
        UssdSession.objects.create(
            phone_number="+256700111111",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        UssdSession.objects.create(
            phone_number="+256700222222",
            expires_at=timezone.now() + timedelta(minutes=9),
        )
        deleted, _ = UssdSession.objects.cleanup_expired()
        self.assertGreater(deleted, 0)
        self.assertFalse(
            UssdSession.objects.filter(phone_number="+256700111111").exists()
        )
        self.assertTrue(
            UssdSession.objects.filter(phone_number="+256700222222").exists()
        )

    def test_is_expired_returns_correctly(self):
        expired = UssdSession.objects.create(
            phone_number="+256700111111",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        active = UssdSession.objects.create(
            phone_number="+256700222222",
        )
        self.assertTrue(expired.is_expired())
        self.assertFalse(active.is_expired())

    @patch("ussd.models.default_session_expires_at")
    def test_reset_clears_state_and_uses_configured_expiry(self, expires_at):
        expected_expiry = timezone.now() + timedelta(minutes=5)
        expires_at.return_value = expected_expiry
        session = UssdSession.objects.create(
            phone_number="+256700111111",
            state="host_broadcast_msg",
            data={"selected_space_id": 42},
        )

        session.reset()

        self.assertEqual(session.state, "main_menu")
        self.assertIsNone(session.space)
        self.assertEqual(session.data, {})
        self.assertEqual(session.expires_at, expected_expiry)
        expires_at.assert_called_once_with()

    def test_session_data_stores_only_ids(self):
        """Session.data must never contain sensitive fields (update.md §5)."""
        session = UssdSession.objects.create(
            phone_number="+256700111111",
            data={"space_id": 42, "survey_id": 17, "question_index": 2},
        )
        data_str = str(session.data).lower()
        self.assertNotIn("pin", data_str)
        self.assertNotIn("password", data_str)
        self.assertNotIn("secret", data_str)


# ==========================================
# Callback – main menu routing
# ==========================================


class UssdMainMenuTests(TestCase):
    def setUp(self):
        self.ussd_url = reverse("ussd-callback")
        self.owner = CustomUser.objects.create_user(
            username="host_owner",
            phone="+256700111111",
            password="pass123",
        )
        self.org = Organization.objects.create(
            owner=self.owner, name="Host Org", sms_balance=100
        )
        self.wallet = Wallet.objects.create(
            organization=self.org, balance_credits=100
        )

    def test_host_sees_host_menu(self):
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": ""},
        )
        body = res.content.decode()
        self.assertIn("Welcome Host to YoSpaces", body)
        self.assertIn("Host a Space", body)
        self.assertIn("Broadcast SMS", body)

    def test_member_sees_member_menu(self):
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256799999999", "text": ""},
        )
        body = res.content.decode()
        self.assertIn("Welcome to YoSpaces", body)
        self.assertIn("Join Space via PIN", body)
        self.assertIn("Browse Public Spaces", body)

    def test_non_post_returns_end(self):
        res = self.client.get(self.ussd_url)
        self.assertIn("END", res.content.decode())


# ==========================================
# Callback – host workflow
# ==========================================


class UssdHostWorkflowTests(TestCase):
    def setUp(self):
        self.ussd_url = reverse("ussd-callback")
        self.owner = CustomUser.objects.create_user(
            username="host_owner",
            phone="+256700111111",
            password="pass123",
        )
        self.org = Organization.objects.create(
            owner=self.owner, name="Host Org", sms_balance=100
        )
        self.wallet = Wallet.objects.create(
            organization=self.org, balance_credits=100
        )
        self.space = Space.objects.create(
            organization=self.org,
            name="Test Space",
            host_phone="+256700111111",
        )
        SpaceMember.objects.create(
            space=self.space,
            phone_number="+256755555555",
            name="Member One",
        )

    def test_host_creates_space(self):
        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": ""},
        )
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "1"},
        )
        self.assertIn("Enter a name for your Space", res.content.decode())

        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "1*NewSpace"},
        )
        body = res.content.decode()
        self.assertIn("created", body)
        self.assertTrue(Space.objects.filter(name="NewSpace").exists())
        self.assertFalse(
            UssdSession.objects.filter(phone_number="+256700111111").exists()
        )

    def test_host_lists_spaces(self):
        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": ""},
        )
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "2"},
        )
        body = res.content.decode()
        self.assertIn("My Spaces", body)
        self.assertIn("Test Space", body)

    def test_host_see_no_spaces_message(self):
        other_owner = CustomUser.objects.create_user(
            username="other_host",
            phone="+256711111111",
            password="pass123",
        )
        Organization.objects.create(
            owner=other_owner, name="Other Org", sms_balance=100
        )
        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256711111111", "text": ""},
        )
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256711111111", "text": "2"},
        )
        self.assertIn("no active spaces", res.content.decode())

    @patch("sms.views.send_bulk_sms")
    def test_host_broadcast_flow_success(self, mock_send):
        mock_send.return_value = {"success": True, "count": 1}

        # Select broadcast (option 3)
        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": ""},
        )
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "3"},
        )
        body = res.content.decode()
        self.assertIn("Select Space to Broadcast", body)
        self.assertIn("Test Space", body)

        # Select space 1
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "3*1"},
        )
        self.assertIn("Enter broadcast SMS message", res.content.decode())

        # Enter message
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "3*1*Hello from YoSpaces"},
        )
        body = res.content.decode()
        self.assertIn("Broadcast sent to 1 members", body)

        record = BroadcastSmsRecord.objects.get()
        self.assertEqual(record.status, "sent")
        self.assertIsNotNone(record.sent_at)
        self.assertIsNotNone(record.usage_record)
        mock_send.assert_called_once()

    @patch("sms.views.send_bulk_sms")
    def test_host_broadcast_insufficient_credits(self, mock_send):
        self.wallet.balance_credits = 0
        self.wallet.save()

        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": ""},
        )
        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "3"},
        )
        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "3*1"},
        )
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "3*1*Hello"},
        )
        self.assertIn("Insufficient SMS credits", res.content.decode())
        mock_send.assert_not_called()
        self.assertFalse(BroadcastSmsRecord.objects.exists())

    @patch("sms.views.send_bulk_sms")
    def test_host_broadcast_refunds_on_provider_failure(self, mock_send):
        mock_send.return_value = {"success": False, "error": "Provider error"}

        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": ""},
        )
        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "3"},
        )
        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "3*1"},
        )
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "3*1*Hello"},
        )
        self.assertIn("SMS credits were refunded", res.content.decode())

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_credits, 100)
        record = BroadcastSmsRecord.objects.get()
        self.assertEqual(record.status, "refunded")

    @patch("sms.views.send_bulk_sms")
    def test_host_cannot_broadcast_to_unowned_space(self, mock_send):
        """A phone that is not a host should not reach the broadcast flow."""
        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256799999999", "text": "3"},
        )
        body = res.content.decode()
        self.assertNotIn("Broadcast", body)
        self.assertNotIn("Select Space", body)
        mock_send.assert_not_called()


# ==========================================
# Callback – member workflow
# ==========================================


class UssdMemberWorkflowTests(TestCase):
    def setUp(self):
        self.ussd_url = reverse("ussd-callback")
        self.owner = CustomUser.objects.create_user(
            username="host_owner",
            phone="+256700111111",
            password="pass123",
        )
        self.org = Organization.objects.create(
            owner=self.owner, name="Host Org", sms_balance=100
        )
        self.wallet = Wallet.objects.create(
            organization=self.org, balance_credits=100
        )
        self.space = Space.objects.create(
            organization=self.org,
            name="Public Space",
            host_phone="+256700111111",
            is_public=True,
        )

    def test_member_join_space_via_pin(self):
        member_phone = "+256799999999"
        self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": ""}
        )
        res = self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": "1"}
        )
        self.assertIn("Enter 4-digit Space PIN", res.content.decode())

        res = self.client.post(
            self.ussd_url,
            {"phoneNumber": member_phone, "text": f"1*{self.space.pin}"},
        )
        body = res.content.decode()
        self.assertIn("Registered", body)
        self.assertTrue(
            SpaceMember.objects.filter(
                space=self.space, phone_number=member_phone
            ).exists()
        )
        self.assertFalse(
            UssdSession.objects.filter(phone_number=member_phone).exists()
        )

    def test_member_invalid_pin(self):
        member_phone = "+256799999999"
        self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": ""}
        )
        self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": "1"}
        )
        res = self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": "1*0000"}
        )
        self.assertIn("Invalid PIN", res.content.decode())

    def test_member_browse_public_spaces(self):
        member_phone = "+256799999999"
        self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": ""}
        )
        res = self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": "2"}
        )
        body = res.content.decode()
        self.assertIn("Public Spaces", body)
        self.assertIn("Public Space", body)

    def test_member_take_active_surveys(self):
        survey = Survey.objects.create(
            space=self.space, title="Community Survey", is_active=True
        )
        SurveyQuestion.objects.create(
            survey=survey,
            question_text="Do you like USSD?",
            question_type="multiple_choice",
            options=["Yes", "No"],
        )

        member_phone = "+256799999999"
        self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": ""}
        )
        res = self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": "3"}
        )
        body = res.content.decode()
        self.assertIn("Active Surveys", body)
        self.assertIn("Community Survey", body)

    def test_member_about(self):
        member_phone = "+256799999999"
        self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": ""}
        )
        res = self.client.post(
            self.ussd_url, {"phoneNumber": member_phone, "text": "4"}
        )
        self.assertIn("2G community communication platform", res.content.decode())


# ==========================================
# Callback – session lifecycle
# ==========================================


class UssdSessionLifecycleTests(TestCase):
    def setUp(self):
        self.ussd_url = reverse("ussd-callback")
        self.owner = CustomUser.objects.create_user(
            username="host_owner",
            phone="+256700111111",
            password="pass123",
        )
        self.org = Organization.objects.create(
            owner=self.owner, name="Host Org", sms_balance=100
        )
        self.space = Space.objects.create(
            organization=self.org,
            name="Lifecycle Space",
            host_phone="+256700111111",
        )

    def test_session_persists_across_requests(self):
        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": ""},
        )
        # Initial request creates session
        self.assertTrue(
            UssdSession.objects.filter(phone_number="+256700111111").exists()
        )

        # Selecting option 1 moves session into host_space_name state
        self.client.post(
            self.ussd_url,
            {"phoneNumber": "+256700111111", "text": "1"},
        )
        session = UssdSession.objects.get(phone_number="+256700111111")
        self.assertEqual(session.state, "host_space_name")

    def test_session_cleared_on_exit(self):
        phone = "+256700111111"
        self.client.post(self.ussd_url, {"phoneNumber": phone, "text": ""})
        self.assertTrue(UssdSession.objects.filter(phone_number=phone).exists())
        self.client.post(self.ussd_url, {"phoneNumber": phone, "text": "5"})
        self.assertFalse(UssdSession.objects.filter(phone_number=phone).exists())

    def test_empty_text_resets_session(self):
        phone = "+256700111111"
        # First interaction: select broadcast
        self.client.post(self.ussd_url, {"phoneNumber": phone, "text": ""})
        self.client.post(self.ussd_url, {"phoneNumber": phone, "text": "3"})
        session = UssdSession.objects.get(phone_number=phone)
        self.assertEqual(session.state, "host_broadcast_select")

        # Second interaction: dials again, session resets
        self.client.post(self.ussd_url, {"phoneNumber": phone, "text": ""})
        session = UssdSession.objects.get(phone_number=phone)
        self.assertEqual(session.state, "main_menu")

    def test_invalid_request_method(self):
        res = self.client.put(self.ussd_url)
        self.assertIn("END", res.content.decode())


# ==========================================
# Service layer
# ==========================================


class UssdBroadcastServiceTests(TestCase):
    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            username="host_owner",
            phone="+256700111111",
            password="pass123",
        )
        self.org = Organization.objects.create(
            owner=self.owner, name="Host Org", sms_balance=100
        )
        self.wallet = Wallet.objects.create(
            organization=self.org, balance_credits=100
        )
        self.space = Space.objects.create(
            organization=self.org,
            name="Test Space",
            host_phone="+256700111111",
        )
        SpaceMember.objects.create(
            space=self.space,
            phone_number="+256755555555",
            name="Member One",
        )

    @patch("sms.views.send_bulk_sms")
    def test_initiate_broadcast_success(self, mock_send):
        mock_send.return_value = {"success": True, "count": 1}

        recipients = ["+256755555555"]
        record, error = initiate_ussd_broadcast(
            space=self.space,
            phone_numbers=recipients,
            message="Hello",
        )
        self.assertIsNone(error)
        self.assertIsNotNone(record)
        self.assertEqual(record.status, "sent")
        self.assertEqual(record.recipient_count, 1)
        self.assertIsNotNone(record.usage_record)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_credits, 99)

    @patch("sms.views.send_bulk_sms")
    def test_initiate_broadcast_insufficient_credits(self, mock_send):
        self.wallet.balance_credits = 0
        self.wallet.save()

        record, error = initiate_ussd_broadcast(
            space=self.space,
            phone_numbers=["+256755555555"],
            message="Hello",
        )
        self.assertIsNone(record)
        self.assertIn("Insufficient SMS credits", error)
        mock_send.assert_not_called()

    @patch("sms.views.send_bulk_sms")
    def test_initiate_broadcast_refund_on_failure(self, mock_send):
        mock_send.return_value = {"success": False, "error": "Down"}

        record, error = initiate_ussd_broadcast(
            space=self.space,
            phone_numbers=["+256755555555"],
            message="Hello",
        )
        self.assertIsNone(record)
        self.assertIn("refunded", error)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_credits, 100)
        rec = BroadcastSmsRecord.objects.get()
        self.assertEqual(rec.status, "refunded")

    def test_initiate_broadcast_no_recipients(self):
        record, error = initiate_ussd_broadcast(
            space=self.space,
            phone_numbers=[],
            message="Hello",
        )
        self.assertIsNone(record)
        self.assertIn("No recipients", error)
