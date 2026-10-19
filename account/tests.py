from django.urls import reverse
from django.test import TestCase
from rest_framework.test import APIClient

from .models import CustomUser, Member, Organization


class AuthLoginTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='StrongPass123!',
        )
        self.organization = Organization.objects.create(
            owner=self.user,
            name='Alice Org',
            default_language='en',
        )
        Member.objects.create(user=self.user, organization=self.organization, role='admin')

    def test_login_with_username_returns_tokens_and_org(self):
        response = self.client.post(
            reverse('auth-login'),
            {'identifier': 'alice', 'password': 'StrongPass123!'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])
        self.assertEqual(response.data['organization']['name'], 'Alice Org')

    def test_login_with_email_returns_tokens_and_org(self):
        response = self.client.post(
            reverse('auth-login'),
            {'identifier': 'alice@example.com', 'password': 'StrongPass123!'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertEqual(response.data['user']['email'], 'alice@example.com')

    def test_login_with_wrong_password_fails_cleanly(self):
        response = self.client.post(
            reverse('auth-login'),
            {'identifier': 'alice', 'password': 'WrongPassword!'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('non_field_errors', response.data)

    def test_registration_creates_user_without_organization(self):
        response = self.client.post(
            reverse('auth-register'),
            {
                'email': 'new.user@example.com',
                'password': 'StrongPass123!',
                'first_name': 'New',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data['organization'])
        self.assertIn('access', response.data['tokens'])
        self.assertTrue(
            CustomUser.objects.filter(email='new.user@example.com').exists()
        )

    def test_registration_rejects_languages_without_translations(self):
        response = self.client.post(
            reverse('auth-register'),
            {
                'email': 'unsupported.language@example.com',
                'password': 'StrongPass123!',
                'default_language': 'sw',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('default_language', response.data)

    def test_user_can_create_organization_after_registration(self):
        registration = self.client.post(
            reverse('auth-register'),
            {
                'email': 'onboard@example.com',
                'password': 'StrongPass123!',
            },
            format='json',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {registration.data['tokens']['access']}"
        )

        response = self.client.post(
            reverse('organization-detail'),
            {'name': 'Onboard Org', 'default_language': 'en'},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        organization = Organization.objects.get(name='Onboard Org')
        self.assertEqual(organization.owner.email, 'onboard@example.com')
        self.assertTrue(
            Member.objects.filter(
                user=organization.owner,
                organization=organization,
                role='admin',
            ).exists()
        )

    def test_dashboard_requires_an_organization_membership(self):
        registration = self.client.post(
            reverse('auth-register'),
            {
                'email': 'dashboard@example.com',
                'password': 'StrongPass123!',
            },
            format='json',
        )
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {registration.data['tokens']['access']}"
        )

        response = self.client.get(reverse('dashboard-stats'))

        self.assertEqual(response.status_code, 403)

        organization_response = self.client.post(
            reverse('organization-detail'),
            {'name': 'Dashboard Org'},
            format='json',
        )
        self.assertEqual(organization_response.status_code, 201)
        organization_id = organization_response.data['id']

        forbidden_response = self.client.get(
            reverse('dashboard-stats'),
            HTTP_X_ORGANIZATION_ID=str(organization_id + 100),
        )
        self.assertEqual(forbidden_response.status_code, 403)

        dashboard_response = self.client.get(
            reverse('dashboard-stats'),
            HTTP_X_ORGANIZATION_ID=str(organization_id),
        )
        self.assertEqual(dashboard_response.status_code, 200)


class OrganizationAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = CustomUser.objects.create_user(
            username="multi_org_owner",
            email="owner@example.com",
            password="StrongPass123!",
        )
        self.first_org = Organization.objects.create(
            owner=self.owner,
            name="First organization",
        )
        self.second_org = Organization.objects.create(
            owner=self.owner,
            name="Second organization",
        )
        self.client.force_authenticate(user=self.owner)

    def test_update_uses_the_selected_owned_organization(self):
        response = self.client.put(
            reverse("organization-detail"),
            {"name": "Updated second organization"},
            HTTP_X_ORGANIZATION_ID=str(self.second_org.id),
        )

        self.assertEqual(response.status_code, 200)
        self.first_org.refresh_from_db()
        self.second_org.refresh_from_db()
        self.assertEqual(self.first_org.name, "First organization")
        self.assertEqual(self.second_org.name, "Updated second organization")

    def test_get_uses_the_selected_owned_organization(self):
        response = self.client.get(
            reverse("organization-detail"),
            HTTP_X_ORGANIZATION_ID=str(self.second_org.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Second organization")

    def test_invalid_selected_organization_does_not_fall_back_to_another_org(self):
        response = self.client.get(
            reverse("organization-detail"),
            HTTP_X_ORGANIZATION_ID="not-an-id",
        )

        self.assertEqual(response.status_code, 404)

    def test_user_cannot_add_members_to_another_organizations(self):
        other_owner = CustomUser.objects.create_user(
            username="other_org_owner",
            email="other@example.com",
            password="StrongPass123!",
        )
        other_org = Organization.objects.create(
            owner=other_owner,
            name="Other organization",
        )

        response = self.client.post(
            reverse("org-member-list"),
            {
                "user": self.owner.id,
                "organization": other_org.id,
                "role": "admin",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Member.objects.filter(
                user=self.owner,
                organization=other_org,
            ).exists()
        )
