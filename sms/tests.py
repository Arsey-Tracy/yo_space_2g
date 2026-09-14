# from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from account.models import CustomUser, Organization
from spaces.models import Space


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
